from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.models import ModelValidationError
from app.service import SkillDraftService
from app.spec_builder import SkillSpecBuilder
from app.store import DraftStore


def _sample_brief() -> dict:
    return {
        "business_goal": "沉淀团队客服重复问答能力，减少重复劳动",
        "applicable_scenarios": ["售前问题回复", "客户异议处理"],
        "trigger_phrases": ["帮我写回复", "客户问价格太高怎么办"],
        "input_materials": ["产品资料", "历史对话记录"],
        "expected_outputs": ["结构化回复草稿", "下一步行动建议"],
        "boundaries": ["仅基于提供资料，不编造信息"],
        "forbidden_scenarios": ["法律建议", "医疗建议"],
        "example_requests": ["客户嫌贵，怎么回应更容易成交"],
        "language": "zh-CN",
    }


class SkillMDWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = Path("D:/Codex/tmp_pycache/skillmd-tests")
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.case_dir = self.tmp_root / f"case-{uuid.uuid4().hex[:8]}"
        self.case_dir.mkdir(parents=True, exist_ok=True)
        root = self.case_dir

        self.store = DraftStore(root / "drafts")
        self.sessions = DraftStore(root / "sessions")
        self.registry = root / "registry"
        self.registry.mkdir(parents=True, exist_ok=True)

        self.service = SkillDraftService(
            store=self.store,
            registry_path=self.registry,
            session_store=self.sessions,
            spec_builder=SkillSpecBuilder(llm_endpoint=None),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.case_dir, ignore_errors=True)

    def test_draft_generation_produces_three_files(self) -> None:
        draft = self.service.create_draft(_sample_brief())
        files = draft["rendered_files"]
        self.assertIn("skills/", next(iter(files.keys())))
        self.assertEqual(3, len(files))
        self.assertIn("validation_report", draft)
        self.assertIn("quality_score", draft)

    def test_missing_required_fields_returns_actionable_error(self) -> None:
        bad = _sample_brief()
        bad["business_goal"] = ""
        bad["trigger_phrases"] = []
        with self.assertRaises(ModelValidationError) as ctx:
            self.service.create_draft(bad)
        report = ctx.exception.to_dict()
        self.assertFalse(report["pass"])
        self.assertGreaterEqual(len(report["suggestions"]), 1)

    def test_similarity_suggestion_is_returned(self) -> None:
        existed = self.registry / "skills" / "help-me-write-reply"
        existed.mkdir(parents=True, exist_ok=True)
        (existed / "SKILL.md").write_text(
            "# Help Me Write Reply\n\n## When To Use\n- 帮我写回复\n- 客户异议处理\n",
            encoding="utf-8",
        )
        draft = self.service.create_draft(_sample_brief())
        self.assertGreaterEqual(len(draft["dedupe_suggestions"]), 1)

    def test_publish_creates_branch_and_commit(self) -> None:
        repo = self.case_dir / "skills-repo"
        repo.mkdir(parents=True, exist_ok=True)

        draft = self.service.create_draft(_sample_brief())
        result = self.service.publish_pr(
            {
                "draft_id": draft["draft_id"],
                "target_repo": str(repo),
                "base_branch": "main",
            }
        )
        self.assertIn("branch", result)
        self.assertTrue(result["branch"].startswith("skillmd/"))
        self.assertEqual(40, len(result["commit_sha"]))
        self.assertTrue(result["pr_url"])
        self.assertTrue((repo / ".skillmd-publish").exists())

    def test_conversation_converges_then_confirms(self) -> None:
        started = self.service.start_conversation({"language": "zh-CN"})
        session_id = started["session_id"]
        self.assertIn("next_question", started)

        answers = [
            "沉淀售前答疑流程",
            "售前答疑,客户异议处理",
            "帮我写一段客户回复,客户预算不够怎么回",
            "产品资料,历史案例",
            "结构化回复草稿,行动建议",
            "仅基于已知资料",
            "法律建议,医疗建议",
            "客户嫌贵怎么回应",
        ]
        turn = started
        for ans in answers:
            turn = self.service.answer_conversation(session_id, {"answer": ans})

        self.assertTrue(turn["is_ready_for_summary"])
        summary = self.service.get_conversation_summary(session_id)
        self.assertEqual([], summary["missing_items"])

        confirmed = self.service.confirm_conversation(session_id, {"confirmed": True})
        self.assertIn("draft_id", confirmed)
        self.assertGreaterEqual(int(confirmed["quality_score"]), 0)

    def test_uncertain_answer_returns_candidates(self) -> None:
        started = self.service.start_conversation({})
        session_id = started["session_id"]
        turn = self.service.answer_conversation(session_id, {"answer": "我不确定"})
        self.assertFalse(turn["is_ready_for_summary"])
        self.assertEqual(3, len(turn.get("options", [])))

    def test_download_skill_md_returns_expected_file(self) -> None:
        draft = self.service.create_draft(_sample_brief())
        filename, content = self.service.get_skill_md_download(draft["draft_id"])
        self.assertTrue(filename.endswith("-skill.md"))
        self.assertIn("## Overview", content)


if __name__ == "__main__":
    unittest.main()
