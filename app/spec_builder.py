from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import SkillBriefV1, SkillSpecV1
from .utils import slugify


class SkillSpecBuilder:
    def __init__(self, llm_endpoint: str | None = None, timeout_seconds: int = 15):
        self.llm_endpoint = llm_endpoint or os.environ.get("SKILLMD_LLM_ENDPOINT")
        self.timeout_seconds = timeout_seconds

    def build(self, brief: SkillBriefV1) -> SkillSpecV1:
        if self.llm_endpoint:
            spec = self._build_with_llm(brief)
            if spec is not None:
                return spec
        return self._build_with_rules(brief)

    def _build_with_llm(self, brief: SkillBriefV1) -> SkillSpecV1 | None:
        payload = {
            "task": "normalize_skill_spec_v1",
            "language": brief.language,
            "brief": brief.to_dict(),
        }
        req = urllib.request.Request(
            self.llm_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            spec = data.get("spec", data)
            if not isinstance(spec, dict):
                return None
            return SkillSpecV1(
                name=slugify(str(spec.get("name", "")), fallback_prefix="team-skill"),
                description=str(spec.get("description", "")).strip(),
                trigger_rules=[str(item).strip() for item in spec.get("trigger_rules", []) if str(item).strip()],
                workflow_steps=[str(item).strip() for item in spec.get("workflow_steps", []) if str(item).strip()],
                safety_notes=[str(item).strip() for item in spec.get("safety_notes", []) if str(item).strip()],
                artifacts=[str(item).strip() for item in spec.get("artifacts", []) if str(item).strip()],
            )
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            return None

    def _build_with_rules(self, brief: SkillBriefV1) -> SkillSpecV1:
        seed_name = brief.trigger_phrases[0] if brief.trigger_phrases else brief.applicable_scenarios[0]
        name = slugify(seed_name, fallback_prefix="team-skill")
        if name.startswith("team-skill-"):
            name = slugify(brief.business_goal, fallback_prefix="team-skill")

        description = (
            f"Use this skill to support {brief.business_goal}. "
            f"It standardizes execution for {brief.applicable_scenarios[0]} and related requests."
        )

        trigger_rules = list(dict.fromkeys(brief.trigger_phrases + brief.applicable_scenarios))

        workflow_steps = [
            "Read all user inputs and required context before drafting output.",
            f"Apply the objective: {brief.business_goal}.",
            "Return structured output that can be reused by teammates.",
        ]
        if brief.expected_outputs:
            workflow_steps.append(f"Ensure the response includes: {brief.expected_outputs[0]}.")

        safety_notes = list(dict.fromkeys(brief.boundaries + brief.forbidden_scenarios))

        artifacts = [
            "SKILL.md",
            "agents/openai.yaml",
            "references/defaults.md",
        ]

        return SkillSpecV1(
            name=name,
            description=description,
            trigger_rules=trigger_rules,
            workflow_steps=workflow_steps,
            safety_notes=safety_notes,
            artifacts=artifacts,
        )

