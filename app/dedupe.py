from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .models import SkillBriefV1, SkillSpecV1


@dataclass
class DedupeSuggestion:
    skill_name: str
    score: float
    reason: str
    recommendation: str

    def to_dict(self) -> dict[str, str | float]:
        return {
            "skill_name": self.skill_name,
            "score": round(self.score, 3),
            "reason": self.reason,
            "recommendation": self.recommendation,
        }


class SimilarityEngine:
    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path)

    def suggest(self, brief: SkillBriefV1, spec: SkillSpecV1) -> list[DedupeSuggestion]:
        candidates = self._load_candidates()
        source = " ".join(
            [
                spec.name,
                spec.description,
                " ".join(spec.trigger_rules),
                brief.business_goal,
                " ".join(brief.trigger_phrases),
            ]
        ).lower()

        suggestions: list[DedupeSuggestion] = []
        for name, text in candidates:
            text_lower = text.lower()
            score = SequenceMatcher(None, source, text_lower).ratio()

            trigger_hit_count = 0
            for phrase in brief.trigger_phrases:
                if phrase.lower() in text_lower:
                    trigger_hit_count += 1
            if brief.trigger_phrases:
                trigger_boost = (trigger_hit_count / len(brief.trigger_phrases)) * 0.45
                score = min(score + trigger_boost, 1.0)

            if score < 0.30:
                continue
            recommendation = "new_skill"
            reason = "有一定相似度，可作为参考。"
            if score >= 0.78:
                recommendation = "reuse_existing"
                reason = "高度相似，优先复用或扩展已有 skill。"
            elif score >= 0.60:
                recommendation = "review_merge"
                reason = "中等相似，建议评估是否合并。"
            suggestions.append(
                DedupeSuggestion(
                    skill_name=name,
                    score=score,
                    reason=reason,
                    recommendation=recommendation,
                )
            )

        suggestions.sort(key=lambda item: item.score, reverse=True)
        return suggestions[:5]

    def _load_candidates(self) -> list[tuple[str, str]]:
        skills_root = self.registry_path / "skills"
        if not skills_root.exists():
            return []
        items: list[tuple[str, str]] = []
        for skill_dir in skills_root.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            items.append((skill_dir.name, text[:5000]))
        return items
