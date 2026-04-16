from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from .conversation import (
    SLOT_ORDER,
    completeness,
    current_slot,
    default_slots,
    looks_uncertain,
    parse_slot_value,
)
from .conversation_agent import ConversationAgent
from .dedupe import SimilarityEngine
from .git_publisher import GitPublisher
from .models import ModelValidationError, SkillBriefV1
from .renderer import render_skill_files
from .spec_builder import SkillSpecBuilder
from .store import DraftStore
from .utils import utc_now_iso
from .validator import validate_draft_payload


class SkillDraftService:
    def __init__(
        self,
        store: DraftStore,
        registry_path: str | Path,
        spec_builder: SkillSpecBuilder | None = None,
        publisher: GitPublisher | None = None,
        session_store: DraftStore | None = None,
        conversation_agent: ConversationAgent | None = None,
    ):
        self.store = store
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.spec_builder = spec_builder or SkillSpecBuilder()
        self.publisher = publisher or GitPublisher()
        self.session_store = session_store or DraftStore(self.store.root_dir.parent / "sessions")
        self.conversation_agent = conversation_agent or ConversationAgent()

    @classmethod
    def from_environment(cls, base_dir: str | Path) -> "SkillDraftService":
        base = Path(base_dir)
        drafts_dir = Path(os.environ.get("SKILLMD_DRAFT_DIR", str(base / "data" / "drafts")))
        sessions_dir = Path(os.environ.get("SKILLMD_SESSION_DIR", str(base / "data" / "sessions")))
        registry_path = Path(os.environ.get("SKILLMD_REGISTRY_PATH", str(base / "skills-registry")))
        return cls(
            store=DraftStore(drafts_dir),
            registry_path=registry_path,
            session_store=DraftStore(sessions_dir),
        )

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = SkillBriefV1.from_dict(payload)
        spec = self.spec_builder.build(brief)

        similarity = SimilarityEngine(self.registry_path).suggest(brief=brief, spec=spec)
        rendered_files = render_skill_files(brief=brief, spec=spec)
        draft_id = uuid.uuid4().hex[:12]

        draft = {
            "draft_id": draft_id,
            "created_at": utc_now_iso(),
            "brief": brief.to_dict(),
            "spec": spec.to_dict(),
            "rendered_files": rendered_files,
            "dedupe_suggestions": [item.to_dict() for item in similarity],
        }
        report = validate_draft_payload(draft)
        draft["validation_report"] = report.to_dict()
        draft["quality_score"] = report.score

        self.store.save(draft_id=draft_id, payload=draft)
        return draft

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._resolve_draft(payload)
        report = validate_draft_payload(draft)
        return report.to_dict()

    def publish_pr(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = self._resolve_draft(payload)
        report = validate_draft_payload(draft)
        if not report.passed:
            raise ModelValidationError(
                [
                    {
                        "field": "draft",
                        "message": "draft 校验未通过，无法发布",
                        "suggestion": "请先调用 /api/skills/validate 修复 errors 后再发布。",
                    }
                ]
            )

        target_repo = payload.get("target_repo")
        if not isinstance(target_repo, str) or not target_repo.strip():
            raise ModelValidationError(
                [
                    {
                        "field": "target_repo",
                        "message": "target_repo 不能为空",
                        "suggestion": "请传入目标 skills-registry Git 仓库绝对路径。",
                    }
                ]
            )
        base_branch = payload.get("base_branch", "main")
        if not isinstance(base_branch, str) or not base_branch.strip():
            base_branch = "main"

        result = self.publisher.publish(
            draft=draft,
            target_repo=target_repo.strip(),
            base_branch=base_branch.strip(),
        )
        return result

    def start_conversation(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = uuid.uuid4().hex[:12]
        slots = default_slots()

        initial_goal = payload.get("initial_goal")
        if isinstance(initial_goal, str) and initial_goal.strip():
            slots["business_goal"] = initial_goal.strip()

        language = payload.get("language")
        if isinstance(language, str) and language.strip():
            slots["language"] = language.strip()

        session = {
            "session_id": session_id,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "status": "collecting",
            "history": [],
            "slots": slots,
            "draft_id": None,
        }
        self.session_store.save(session_id, session)
        return self._conversation_turn(session, intro=True)

    def answer_conversation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.session_store.load(session_id)
        if session.get("status") == "completed":
            return {
                "session_id": session_id,
                "assistant_message": "会话已经完成，你可以直接下载或发布已有草稿。",
                "is_ready_for_summary": True,
                "progress": completeness(session.get("slots", {})),
            }

        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ModelValidationError(
                [
                    {
                        "field": "answer",
                        "message": "answer 不能为空",
                        "suggestion": "请回答当前问题，若不确定可直接输入“我不确定”。",
                    }
                ]
            )

        slots = session.get("slots", default_slots())
        slot = current_slot(slots)
        if slot is None:
            session["status"] = "ready_for_summary"
            session["updated_at"] = utc_now_iso()
            self.session_store.save(session_id, session)
            return self._conversation_turn(session)

        if looks_uncertain(answer):
            return self._conversation_turn(session, uncertain=True)

        parsed = parse_slot_value(slot, answer)
        slots[slot] = parsed
        session.setdefault("history", []).append({"slot": slot, "answer": answer.strip(), "at": utc_now_iso()})
        session["slots"] = slots
        session["updated_at"] = utc_now_iso()

        if current_slot(slots) is None:
            session["status"] = "ready_for_summary"

        self.session_store.save(session_id, session)
        return self._conversation_turn(session)

    def get_conversation_summary(self, session_id: str) -> dict[str, Any]:
        session = self.session_store.load(session_id)
        slots = session.get("slots", default_slots())
        missing = [key for key in SLOT_ORDER if not self._slot_has_value(key, slots.get(key))]

        summary_brief = {
            "business_goal": slots.get("business_goal", ""),
            "applicable_scenarios": slots.get("applicable_scenarios", []),
            "trigger_phrases": slots.get("trigger_phrases", []),
            "input_materials": slots.get("input_materials", []),
            "expected_outputs": slots.get("expected_outputs", []),
            "boundaries": slots.get("boundaries", []),
            "forbidden_scenarios": slots.get("forbidden_scenarios", []),
            "example_requests": slots.get("example_requests", []),
            "language": slots.get("language", "zh-CN"),
        }

        return {
            "session_id": session_id,
            "summary_brief": summary_brief,
            "missing_items": missing,
            "completeness_score": completeness(slots),
            "confidence": round(completeness(slots) / 100.0, 2),
        }

    def confirm_conversation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.session_store.load(session_id)
        confirmed = payload.get("confirmed")
        if confirmed is not True:
            raise ModelValidationError(
                [
                    {
                        "field": "confirmed",
                        "message": "confirmed 必须为 true",
                        "suggestion": "请在摘要确认后传 confirmed=true。",
                    }
                ]
            )

        summary = self.get_conversation_summary(session_id)
        missing = summary.get("missing_items", [])
        if missing:
            raise ModelValidationError(
                [
                    {
                        "field": "summary",
                        "message": "信息尚未收敛完成，无法生成草稿",
                        "suggestion": "请继续回答问题，直到缺失项清零。",
                    }
                ]
            )

        draft = self.create_draft(summary["summary_brief"])
        session["status"] = "completed"
        session["draft_id"] = draft["draft_id"]
        session["updated_at"] = utc_now_iso()
        self.session_store.save(session_id, session)

        return {
            "session_id": session_id,
            "draft_id": draft["draft_id"],
            "quality_score": draft["quality_score"],
            "validation_report": draft["validation_report"],
            "dedupe_suggestions": draft["dedupe_suggestions"],
            "spec_name": draft.get("spec", {}).get("name"),
            "rendered_files": list(draft.get("rendered_files", {}).keys()),
        }

    def get_skill_md_download(self, draft_id: str) -> tuple[str, str]:
        draft = self.store.load(draft_id)
        spec_name = str(draft.get("spec", {}).get("name", "skill")).strip() or "skill"
        skill_path = f"skills/{spec_name}/SKILL.md"
        rendered_files = draft.get("rendered_files", {})
        if skill_path not in rendered_files:
            raise FileNotFoundError(f"SKILL.md not found in draft: {draft_id}")

        content = str(rendered_files[skill_path])
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", spec_name).strip("-") or "skill"
        filename = f"{safe_name}-skill.md"
        return filename, content

    def _conversation_turn(
        self,
        session: dict[str, Any],
        intro: bool = False,
        uncertain: bool = False,
    ) -> dict[str, Any]:
        slots = session.get("slots", default_slots())
        slot = current_slot(slots)
        progress = completeness(slots)
        turn = self.conversation_agent.generate_turn(
            slots=slots,
            history=session.get("history", []),
            current_slot=slot,
            intro=intro,
            uncertain=uncertain,
        )
        return {
            "session_id": session["session_id"],
            "assistant_message": turn.get("assistant_message", ""),
            "next_question": turn.get("next_question"),
            "options": turn.get("options", []),
            "current_slot": slot,
            "is_ready_for_summary": slot is None,
            "progress": progress,
        }

    def _slot_has_value(self, slot: str, value: Any) -> bool:
        if slot == "business_goal":
            return isinstance(value, str) and bool(value.strip())
        return isinstance(value, list) and len([item for item in value if str(item).strip()]) > 0

    def _resolve_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "draft_id" in payload and isinstance(payload["draft_id"], str):
            return self.store.load(payload["draft_id"])
        if "spec" in payload and "rendered_files" in payload:
            return payload
        raise ModelValidationError(
            [
                {
                    "field": "payload",
                    "message": "需要提供 draft_id 或完整 draft 对象",
                    "suggestion": "请传入 draft_id，或包含 spec 与 rendered_files 的对象。",
                }
            ]
        )
