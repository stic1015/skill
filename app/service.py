from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

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
    ):
        self.store = store
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.spec_builder = spec_builder or SkillSpecBuilder()
        self.publisher = publisher or GitPublisher()

    @classmethod
    def from_environment(cls, base_dir: str | Path) -> "SkillDraftService":
        base = Path(base_dir)
        drafts_dir = Path(os.environ.get("SKILLMD_DRAFT_DIR", str(base / "data" / "drafts")))
        registry_path = Path(os.environ.get("SKILLMD_REGISTRY_PATH", str(base / "skills-registry")))
        return cls(store=DraftStore(drafts_dir), registry_path=registry_path)

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

