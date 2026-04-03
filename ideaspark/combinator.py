"""Random recipe: k slots, each slot picks a category (with replacement) then a word."""

from __future__ import annotations

import random
from typing import Any, TypedDict


class Recipe(TypedDict):
    # 有序列表：同一维度可出现多次，如 [(技术,词A),(技术,词B)]
    parts: list[tuple[str, str]]
    summary: str
    word_count: int
    combo_mode: str


def recipe_pairs(parts: Any) -> list[tuple[str, str]]:
    """兼容旧版 dict 或新版 list[[a,b],...]。"""
    if not parts:
        return []
    if isinstance(parts, dict):
        return list(parts.items())
    out: list[tuple[str, str]] = []
    for item in parts:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]), str(item[1])))
    return out


def _non_empty_categories(categories: dict[str, list[str]]) -> list[str]:
    return [k for k, words in categories.items() if words]


def _resolve_k(mode: Any, num_cats: int) -> int:
    """词槽数量：与「有几类有词」脱钩，允许同类多槽（如 技术+技术）。"""
    if num_cats <= 0:
        return 0
    if mode == "random":
        return random.choice([2, 3, 4])
    want = int(mode)
    return max(1, want)


def _pick_word_avoid_dup(
    words: list[str], used_in_category: set[str]
) -> str:
    if not words:
        return "（暂无词，请补充）"
    avail = [w for w in words if w not in used_in_category]
    if avail:
        return random.choice(avail)
    return random.choice(words)


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
            "parts": [],
            "summary": "（请先在词库中补充词汇）",
            "word_count": 0,
            "combo_mode": str(combo_mode),
        }

    # 有放回：同一维度可多次出现
    slots = [random.choice(names) for _ in range(k)]
    used_words: dict[str, set[str]] = {}
    parts_list: list[tuple[str, str]] = []

    for cat in slots:
        words = categories[cat]
        used = used_words.setdefault(cat, set())
        w = _pick_word_avoid_dup(words, used)
        used.add(w)
        parts_list.append((cat, w))

    summary = " × ".join(f"{a}:{b}" for a, b in parts_list)
    mode_label = (
        "随机2–4词（维度可重复）"
        if combo_mode == "random"
        else f"{combo_mode}词组合（维度可重复）"
    )
    return {
        "parts": parts_list,
        "summary": summary,
        "word_count": len(parts_list),
        "combo_mode": mode_label,
    }
