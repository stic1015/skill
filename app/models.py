from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


class ModelValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("Payload validation failed")
        self.errors = errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": False,
            "errors": [f"{entry['field']}: {entry['message']}" for entry in self.errors],
            "warnings": [],
            "suggestions": [entry["suggestion"] for entry in self.errors if entry.get("suggestion")],
            "score": 0,
            "details": self.errors,
        }


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


@dataclass
class SkillBriefV1:
    business_goal: str
    applicable_scenarios: list[str]
    trigger_phrases: list[str]
    input_materials: list[str]
    expected_outputs: list[str]
    boundaries: list[str]
    forbidden_scenarios: list[str]
    example_requests: list[str]
    language: str = "zh-CN"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SkillBriefV1":
        errors: list[dict[str, str]] = []

        def _required_text(field: str, label: str) -> str:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    {
                        "field": field,
                        "message": f"{label}不能为空",
                        "suggestion": f"请补充 {label}，并用一句话说明业务价值。",
                    }
                )
                return ""
            return value.strip()

        goal = _required_text("business_goal", "业务目标")
        scenarios = _as_string_list(payload.get("applicable_scenarios"))
        triggers = _as_string_list(payload.get("trigger_phrases"))
        inputs = _as_string_list(payload.get("input_materials"))
        outputs = _as_string_list(payload.get("expected_outputs"))
        boundaries = _as_string_list(payload.get("boundaries"))
        forbidden = _as_string_list(payload.get("forbidden_scenarios"))
        examples = _as_string_list(payload.get("example_requests"))

        required_lists: list[tuple[str, list[str], str]] = [
            ("applicable_scenarios", scenarios, "适用场景"),
            ("trigger_phrases", triggers, "触发词"),
            ("input_materials", inputs, "输入材料"),
            ("expected_outputs", outputs, "输出期望"),
            ("boundaries", boundaries, "边界"),
            ("forbidden_scenarios", forbidden, "禁用场景"),
            ("example_requests", examples, "示例问法"),
        ]
        for key, values, label in required_lists:
            if not values:
                errors.append(
                    {
                        "field": key,
                        "message": f"{label}至少提供 1 条",
                        "suggestion": f"请补充 {label}，建议先写 3 条可执行内容。",
                    }
                )

        language = payload.get("language", "zh-CN")
        if not isinstance(language, str) or not language.strip():
            language = "zh-CN"

        if errors:
            raise ModelValidationError(errors)

        return cls(
            business_goal=goal,
            applicable_scenarios=scenarios,
            trigger_phrases=triggers,
            input_materials=inputs,
            expected_outputs=outputs,
            boundaries=boundaries,
            forbidden_scenarios=forbidden,
            example_requests=examples,
            language=language.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillSpecV1:
    name: str
    description: str
    trigger_rules: list[str]
    workflow_steps: list[str]
    safety_notes: list[str]
    artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationReportV1:
    passed: bool
    errors: list[str]
    warnings: list[str]
    suggestions: list[str]
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "score": self.score,
        }

