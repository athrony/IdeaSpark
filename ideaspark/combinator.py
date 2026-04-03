"""Random recipe from one word per category."""

from __future__ import annotations

import random
from typing import TypedDict


class Recipe(TypedDict):
    """One word per category key."""

    parts: dict[str, str]
    summary: str


def draw_recipe(categories: dict[str, list[str]], seed: int | None = None) -> Recipe:
    if seed is not None:
        random.seed(seed)
    parts: dict[str, str] = {}
    for name, words in categories.items():
        if not words:
            parts[name] = "（暂无词，请补充）"
        else:
            parts[name] = random.choice(words)
    # Short one-line summary for AI / display
    order = list(parts.keys())
    summary = " × ".join(f"{k}:{parts[k]}" for k in order)
    return Recipe(parts=parts, summary=summary)
