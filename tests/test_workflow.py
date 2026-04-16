from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import shutil
import uuid

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


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


class SkillMDWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = Path("D:/Codex/tmp_pycache/skillmd-tests")
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.case_dir = self.tmp_root / f"case-{uuid.uuid4().hex[:8]}"
        self.case_dir.mkdir(parents=True, exist_ok=True)
        root = self.case_dir
        self.store = DraftStore(root / "drafts")
        self.registry = root / "registry"
        self.registry.mkdir(parents=True, exist_ok=True)
        self.service = SkillDraftService(
            store=self.store,
            registry_path=self.registry,
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


if __name__ == "__main__":
    unittest.main()
