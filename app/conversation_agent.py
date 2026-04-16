from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .conversation import SLOT_OPTIONS, SLOT_QUESTIONS


class ConversationAgent:
    def __init__(self, llm_endpoint: str | None = None, timeout_seconds: int = 15):
        self.llm_endpoint = llm_endpoint or os.environ.get("SKILLMD_CONVERSATION_LLM_ENDPOINT") or os.environ.get(
            "SKILLMD_LLM_ENDPOINT"
        )
        self.timeout_seconds = timeout_seconds

    def generate_turn(
        self,
        *,
        slots: dict[str, Any],
        history: list[dict[str, Any]],
        current_slot: str | None,
        intro: bool,
        uncertain: bool,
    ) -> dict[str, Any]:
        if self.llm_endpoint:
            llm_turn = self._generate_with_llm(
                slots=slots,
                history=history,
                current_slot=current_slot,
                intro=intro,
                uncertain=uncertain,
            )
            if llm_turn is not None:
                return llm_turn
        return self._generate_with_rules(current_slot=current_slot, intro=intro, uncertain=uncertain)

    def _generate_with_llm(
        self,
        *,
        slots: dict[str, Any],
        history: list[dict[str, Any]],
        current_slot: str | None,
        intro: bool,
        uncertain: bool,
    ) -> dict[str, Any] | None:
        payload = {
            "task": "skill_conversation_turn_v1",
            "language": slots.get("language", "zh-CN"),
            "intro": intro,
            "uncertain": uncertain,
            "current_slot": current_slot,
            "slots": slots,
            "history": history[-12:],
            "slot_question": SLOT_QUESTIONS.get(current_slot or "", ""),
            "candidate_options": SLOT_OPTIONS.get(current_slot or "", [])[:3],
            "instruction": (
                "请返回 JSON，字段包括 assistant_message(必填字符串), "
                "next_question(字符串或 null), options(字符串数组，最多3项)。"
            ),
        }
        req = urllib.request.Request(
            self.llm_endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            turn = data.get("turn", data)
            if not isinstance(turn, dict):
                return None

            assistant_message = str(turn.get("assistant_message", "")).strip()
            next_question = turn.get("next_question")
            options = turn.get("options")

            if next_question is not None:
                next_question = str(next_question).strip()
            if not isinstance(options, list):
                options = []
            options = [str(item).strip() for item in options if str(item).strip()]

            if not assistant_message:
                return None
            if current_slot and not next_question:
                next_question = SLOT_QUESTIONS.get(current_slot, "")
            if not uncertain:
                options = []

            return {
                "assistant_message": assistant_message,
                "next_question": next_question if next_question else None,
                "options": options[:3],
            }
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            return None

    def _generate_with_rules(self, *, current_slot: str | None, intro: bool, uncertain: bool) -> dict[str, Any]:
        if current_slot is None:
            return {
                "assistant_message": "信息已经收集完整。请查看摘要并确认生成。",
                "next_question": None,
                "options": [],
            }

        if uncertain:
            return {
                "assistant_message": "没问题，我们先用候选项快速收敛。选一个最接近的，或者直接改写。",
                "next_question": SLOT_QUESTIONS[current_slot],
                "options": SLOT_OPTIONS.get(current_slot, [])[:3],
            }

        intro_text = "我们一步一步来，我每次只问一个关键问题。"
        return {
            "assistant_message": intro_text if intro else "收到，我们继续下一步。",
            "next_question": SLOT_QUESTIONS[current_slot],
            "options": [],
        }
