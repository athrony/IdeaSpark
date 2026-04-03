"""Random recipe: pick 2–4 words from distinct categories."""

from __future__ import annotations

import random
from typing import Any, TypedDict


class Recipe(TypedDict):
    parts: dict[str, str]
    summary: str
    word_count: int
    combo_mode: str


def _non_empty_categories(categories: dict[str, list[str]]) -> list[str]:
    return [k for k, words in categories.items() if words]


def _resolve_k(mode: Any, num_cats: int) -> int:
    """How many categories to sample (words in the recipe)."""
    if num_cats <= 0:
        return 0
    if mode == "random":
        if num_cats == 1:
            return 1
        if num_cats == 2:
            return 2
        if num_cats == 3:
            return random.choice([2, 3])
        return random.choice([2, 3, 4])
    want = int(mode)
    return max(1, min(want, num_cats))


def draw_recipe(
    categories: dict[str, list[str]],
    combo_mode: Any = "random",
    seed: int | None = None,
) -> Recipe:
    if seed is not None:
        random.seed(seed)

    names = _non_empty_categories(categories)
    k = _resolve_k(combo_mode, len(names))
    if k == 0:
        return {
            "parts": {},
            "summary": "（请先在词库中补充词汇）",
            "word_count": 0,
            "combo_mode": str(combo_mode),
        }

    picked = random.sample(names, k)
    random.shuffle(picked)

    parts: dict[str, str] = {}
    for name in picked:
        words = categories[name]
        parts[name] = random.choice(words) if words else "（暂无词，请补充）"

    summary = " × ".join(f"{key}:{parts[key]}" for key in picked)
    mode_label = (
        "随机2–4词"
        if combo_mode == "random"
        else f"{combo_mode}词组合"
    )
    return {
        "parts": parts,
        "summary": summary,
        "word_count": len(parts),
        "combo_mode": mode_label,
    }
