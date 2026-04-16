from __future__ import annotations

import re

from .models import ValidationReportV1


REQUIRED_SKILL_HEADINGS = [
    "## Overview",
    "## When To Use",
    "## Required Workflow",
    "## Safety Boundaries",
    "## Output Expectations",
]
CONFLICT_TERMS = ["万能", "all-purpose", "anything"]


def validate_draft_payload(draft: dict) -> ValidationReportV1:
    errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []

    spec = draft.get("spec", {})
    files = draft.get("rendered_files", {})

    if not isinstance(spec, dict):
        errors.append("spec 必须是对象。")
        return ValidationReportV1(False, errors, warnings, suggestions, 0)
    if not isinstance(files, dict):
        errors.append("rendered_files 必须是对象。")
        return ValidationReportV1(False, errors, warnings, suggestions, 0)

    name = str(spec.get("name", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,54}", name):
        errors.append("spec.name 必须是 3-55 位小写字母/数字/中横线 slug。")
        suggestions.append("例如使用 `customer-insight-assistant`。")

    desc = str(spec.get("description", "")).strip()
    if len(desc) < 20:
        errors.append("spec.description 长度过短。")
        suggestions.append("请补充目标、范围和输出价值。")
    if len(desc) > 260:
        warnings.append("spec.description 偏长，建议控制在 260 字符以内。")

    required_paths = [
        f"skills/{name}/SKILL.md",
        f"skills/{name}/agents/openai.yaml",
        f"skills/{name}/references/defaults.md",
    ]
    for path in required_paths:
        if path not in files:
            errors.append(f"缺失渲染文件: {path}")

    skill_path = f"skills/{name}/SKILL.md"
    skill_content = str(files.get(skill_path, ""))
    for heading in REQUIRED_SKILL_HEADINGS:
        if heading not in skill_content:
            errors.append(f"SKILL.md 缺少段落: {heading}")

    lowered = (desc + " " + " ".join(spec.get("trigger_rules", []))).lower()
    for term in CONFLICT_TERMS:
        if term in lowered:
            warnings.append(f"检测到潜在冲突词: {term}")
            suggestions.append("避免将 skill 描述为可处理任何任务，建议限定边界。")

    score = 100 - len(errors) * 20 - len(warnings) * 5
    score = max(min(score, 100), 0)

    return ValidationReportV1(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        suggestions=suggestions,
        score=score,
    )

