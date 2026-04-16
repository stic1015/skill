from __future__ import annotations

from .models import SkillBriefV1, SkillSpecV1
from .utils import display_name_from_slug


def render_skill_files(brief: SkillBriefV1, spec: SkillSpecV1) -> dict[str, str]:
    slug = spec.name
    display_name = display_name_from_slug(slug)
    skill_md = _render_skill_md(brief=brief, spec=spec, display_name=display_name)
    openai_yaml = _render_openai_yaml(slug=slug, description=spec.description)
    defaults_md = _render_defaults_md(brief=brief, spec=spec)
    return {
        f"skills/{slug}/SKILL.md": skill_md,
        f"skills/{slug}/agents/openai.yaml": openai_yaml,
        f"skills/{slug}/references/defaults.md": defaults_md,
    }


def _render_skill_md(brief: SkillBriefV1, spec: SkillSpecV1, display_name: str) -> str:
    when_to_use = "\n".join(f"- {item}" for item in brief.applicable_scenarios)
    workflow = "\n".join(f"{index}. {step}" for index, step in enumerate(spec.workflow_steps, start=1))
    safety = "\n".join(f"- {item}" for item in spec.safety_notes)
    outputs = "\n".join(f"- {item}" for item in brief.expected_outputs)
    examples = "\n".join(f"- {item}" for item in brief.example_requests)
    return f"""---
name: {spec.name}
description: {spec.description}
---

# {display_name}

## Overview

Use this skill to turn repeatable team requests into stable, reusable workflows with consistent output quality.

## When To Use

{when_to_use}

## Required Workflow

{workflow}

## Safety Boundaries

{safety}

## Output Expectations

{outputs}

## Example Requests

{examples}
"""


def _render_openai_yaml(slug: str, description: str) -> str:
    short_desc = description.strip()
    if len(short_desc) > 110:
        short_desc = short_desc[:107].rstrip() + "..."
    return f"""interface:
  display_name: "{display_name_from_slug(slug)}"
  short_description: "{short_desc}"
  default_prompt: "Use $${slug} to complete this request with the team standard workflow."
policy:
  allow_implicit_invocation: true
"""


def _render_defaults_md(brief: SkillBriefV1, spec: SkillSpecV1) -> str:
    triggers = "\n".join(f"- {item}" for item in spec.trigger_rules)
    boundaries = "\n".join(f"- {item}" for item in brief.boundaries)
    forbidden = "\n".join(f"- {item}" for item in brief.forbidden_scenarios)
    return f"""# {spec.name} defaults

## Business Goal

- {brief.business_goal}

## Trigger Rules

{triggers}

## Boundaries

{boundaries}

## Forbidden Scenarios

{forbidden}
"""

