"""WMS skill discovery and lightweight intent matching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import default_skill_root


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: str
    body: str


@dataclass(frozen=True)
class SkillMatch:
    skill: Skill
    score: int
    reasons: list[str]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "name": self.skill.name,
            "description": self.skill.description,
            "path": self.skill.path,
            "reasons": self.reasons,
            "score": self.score,
        }


KEYWORDS_BY_SKILL = {
    "wms-agent-operator": [
        "receiving",
        "receive",
        "putaway",
        "picking",
        "pick",
        "shipping",
        "ship",
        "inventory",
        "庫存",
        "入庫",
        "出庫",
        "上架",
        "揀貨",
    ],
    "wms-fulfillment-operator": [
        "putaway",
        "picking",
        "pick",
        "shipping",
        "ship",
        "pack",
        "上架",
        "揀貨",
        "發貨",
        "打包",
    ],
    "wms-inventory-operator": [
        "inventory",
        "sku",
        "stock",
        "hold",
        "release",
        "adjust",
        "count",
        "庫存",
        "盤點",
        "凍結",
        "釋放",
        "調整",
    ],
    "wms-receiving-operator": [
        "receiving",
        "receive",
        "inbound",
        "dock",
        "scan",
        "入庫",
        "入库",
    ],
    "wms-recovery-debugger": [
        "error",
        "failed",
        "retry",
        "recover",
        "evidence",
        "錯誤",
        "错误",
        "恢復",
        "恢复",
    ],
    "wms-release-gate-verifier": [
        "release",
        "deploy",
        "ci",
        "smoke",
        "verify",
        "發布",
        "发布",
        "驗證",
        "验证",
    ],
    "wms-local-agent-operator": [
        "local agent",
        "agent shell",
        "local shell",
        "model agent",
        "confirmation",
        "audit",
        "deepseek",
        "qwen",
        "kimi",
        "minimax",
        "本地",
        "确认",
        "審計",
        "审计",
    ],
    "wms-wcs-operator": [
        "wcs",
        "agv",
        "dispatch",
        "callback",
        "replay",
        "gate check",
        "binding",
        "point mapping",
        "transport task",
        "搬运",
        "调度",
        "回调",
        "绑定",
    ],
    "wms-roundtable": [
        "decision",
        "design",
        "plan",
        "risk",
        "review",
        "決策",
        "設計",
        "方案",
    ],
}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, parts[2].strip()


class SkillRegistry:
    def __init__(self, skill_root: Path | None = None) -> None:
        self.skill_root = skill_root or default_skill_root()

    def discover(self) -> list[Skill]:
        if not self.skill_root.exists():
            return []
        skills: list[Skill] = []
        for skill_file in sorted(self.skill_root.glob("*/SKILL.md")):
            text = skill_file.read_text(encoding="utf-8")
            metadata, body = _parse_frontmatter(text)
            name = metadata.get("name") or skill_file.parent.name
            description = metadata.get("description") or ""
            skills.append(
                Skill(
                    name=name,
                    description=description,
                    path=str(skill_file),
                    body=body,
                )
            )
        return skills

    def list_wms_skills(self) -> list[dict[str, str]]:
        return [
            {"name": skill.name, "description": skill.description, "path": skill.path}
            for skill in self.discover()
        ]

    def explain_selection(self, prompt: str, limit: int = 2) -> list[SkillMatch]:
        prompt_lower = prompt.lower()
        scored: list[SkillMatch] = []
        for skill in self.discover():
            keywords = KEYWORDS_BY_SKILL.get(skill.name, [])
            matched_keywords = [keyword for keyword in keywords if keyword.lower() in prompt_lower]
            score = len(matched_keywords)
            reasons = [f"matched keyword: {keyword}" for keyword in matched_keywords[:5]]
            if skill.name in prompt_lower:
                score += 3
                reasons.append("skill name mentioned")
            if score:
                scored.append(SkillMatch(skill=skill, score=score, reasons=reasons))
        scored.sort(key=lambda item: (-item.score, item.skill.name))
        return scored[:limit]

    def select(self, prompt: str, limit: int = 2) -> list[Skill]:
        return [match.skill for match in self.explain_selection(prompt, limit=limit)]

    def select_for_intent(self, prompt: str, limit: int = 2) -> list[dict[str, object]]:
        return [
            {
                "name": match.skill.name,
                "description": match.skill.description,
                "path": match.skill.path,
                "reasons": match.reasons,
                "score": match.score,
            }
            for match in self.explain_selection(prompt, limit=limit)
        ]
