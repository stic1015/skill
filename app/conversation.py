from __future__ import annotations

import re
from typing import Any


SLOT_ORDER: list[str] = [
    "business_goal",
    "applicable_scenarios",
    "trigger_phrases",
    "input_materials",
    "expected_outputs",
    "boundaries",
    "forbidden_scenarios",
    "example_requests",
]

SLOT_QUESTIONS: dict[str, str] = {
    "business_goal": "这个 skill 最想解决什么重复劳动？请用一句话描述。",
    "applicable_scenarios": "它主要在哪些场景使用？请给 2-3 条。",
    "trigger_phrases": "用户通常会怎么提这个请求？请给 2-4 句原话。",
    "input_materials": "AI 需要哪些输入材料才能做得好？请列 2-5 条。",
    "expected_outputs": "你期望它输出什么结果？请列 2-4 条。",
    "boundaries": "这个 skill 的边界是什么？哪些情况需要谨慎处理？",
    "forbidden_scenarios": "明确禁止处理的场景有哪些？请列至少 1 条。",
    "example_requests": "最后给 2-3 条真实示例请求，方便触发和测试。",
}

SLOT_OPTIONS: dict[str, list[str]] = {
    "business_goal": [
        "减少重复问答劳动，统一回复质量",
        "让新成员也能快速产出达标结果",
        "把零散经验沉淀成可复用流程",
    ],
    "applicable_scenarios": [
        "售前咨询和异议处理",
        "需求澄清与方案初稿",
        "项目复盘与经验总结",
    ],
    "trigger_phrases": [
        "帮我写一版可直接发给客户的回复",
        "这个需求怎么拆解成执行步骤",
        "把这段对话整理成标准输出模板",
    ],
    "input_materials": [
        "产品资料和历史案例",
        "用户原始问题和上下文",
        "团队已有 SOP 或知识文档",
    ],
    "expected_outputs": [
        "结构化回复草稿",
        "可执行步骤清单",
        "风险提示与边界说明",
    ],
    "boundaries": [
        "仅基于提供资料，不编造事实",
        "不承诺业务结果",
        "信息不足时先提澄清问题",
    ],
    "forbidden_scenarios": [
        "法律建议",
        "医疗建议",
        "任何需要人工审批的最终决策",
    ],
    "example_requests": [
        "客户说预算不够，帮我给出三段式回应",
        "把这份需求整理成可执行任务列表",
        "用统一模板总结这次沟通结论",
    ],
}

UNCERTAIN_PATTERNS: list[str] = [
    "不确定",
    "不知道",
    "随便",
    "都行",
    "没想好",
    "不清楚",
    "你定",
]


def default_slots() -> dict[str, Any]:
    return {
        "business_goal": "",
        "applicable_scenarios": [],
        "trigger_phrases": [],
        "input_materials": [],
        "expected_outputs": [],
        "boundaries": [],
        "forbidden_scenarios": [],
        "example_requests": [],
        "language": "zh-CN",
    }


def current_slot(slots: dict[str, Any]) -> str | None:
    for key in SLOT_ORDER:
        if not is_slot_filled(key, slots.get(key)):
            return key
    return None


def is_slot_filled(slot: str, value: Any) -> bool:
    if slot == "business_goal":
        return isinstance(value, str) and bool(value.strip())
    return isinstance(value, list) and len([item for item in value if str(item).strip()]) > 0


def completeness(slots: dict[str, Any]) -> int:
    filled = 0
    for key in SLOT_ORDER:
        if is_slot_filled(key, slots.get(key)):
            filled += 1
    return int((filled / len(SLOT_ORDER)) * 100)


def looks_uncertain(answer: str) -> bool:
    text = answer.strip().lower()
    if not text:
        return True
    for pattern in UNCERTAIN_PATTERNS:
        if pattern in text:
            return True
    return False


def parse_slot_value(slot: str, answer: str) -> str | list[str]:
    clean = answer.strip()
    if slot == "business_goal":
        return clean
    parts = re.split(r"[\n,，;；、]+", clean)
    items: list[str] = []
    for part in parts:
        candidate = part.strip()
        if candidate and candidate not in items:
            items.append(candidate)
    return items

