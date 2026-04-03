"""Random recipe: k slots; optional anchor, correlation (business vs chaos), category order weights."""

from __future__ import annotations

import random
from typing import Any, TypedDict

# 高关联时优先抽的「落地」维度（其余为狂想/文艺向池）
BUSINESS_TILT: frozenset[str] = frozenset({"行业", "技术", "人群", "心理需求"})


class Recipe(TypedDict):
    parts: list[tuple[str, str]]
    summary: str
    word_count: int
    combo_mode: str


def recipe_nouns_join(recipe: dict[str, Any] | Any) -> str:
    """仅名词/词组合（无维度前缀），用于清晰展示。"""
    parts = recipe_pairs(recipe.get("parts") if isinstance(recipe, dict) else recipe)
    return " · ".join(w for _, w in parts) if parts else "（空）"


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
    if num_cats <= 0:
        return 0
    if mode == "random":
        return random.choice([2, 3, 4])
    want = int(mode)
    return max(1, want)


def _pick_word_avoid_dup(words: list[str], used_in_category: set[str]) -> str:
    if not words:
        return "（暂无词，请补充）"
    avail = [w for w in words if w not in used_in_category]
    if avail:
        return random.choice(avail)
    return random.choice(words)


def _pick_category(
    names: list[str],
    correlation: float,
    category_order: list[str] | None,
) -> str:
    """
    correlation→1：多数时候进「落地」维度池，并按拖拽顺序加权（越靠前越优先）。
    correlation→0：纯混沌（全维度均匀随机，不受顺序权重影响）。
    """
    c = max(0.0, min(1.0, correlation))
    chaos = random.random() >= c
    if chaos:
        return random.choice(names)
    pool = [n for n in names if n in BUSINESS_TILT] or list(names)
    if category_order and len(pool) > 1:
        rank = {n: i for i, n in enumerate(category_order)}
        weights = [1.0 / (rank.get(p, 10**6) + 1) for p in pool]
        return random.choices(pool, weights=weights, k=1)[0]
    return random.choice(pool)


def draw_recipe(
    categories: dict[str, list[str]],
    combo_mode: Any = "random",
    seed: int | None = None,
    *,
    correlation: float = 0.45,
    anchor_category: str | None = None,
    anchor_word: str | None = None,
    category_order: list[str] | None = None,
) -> Recipe:
    if seed is not None:
        random.seed(seed)

    names = _non_empty_categories(categories)
    k = _resolve_k(combo_mode, len(names))
    if k == 0:
        return {
            "parts": [],
            "summary": "（请先在概念库中补充概念）",
            "word_count": 0,
            "combo_mode": str(combo_mode),
        }

    used_words: dict[str, set[str]] = {}
    parts_list: list[tuple[str, str]] = []

    anchor_cat = (anchor_category or "").strip()
    anchor_txt = (anchor_word or "").strip()

    # 必选锚点：首槽固定（可填词库外自定义词，如「金融交易」）
    if anchor_cat and anchor_cat in names:
        words = categories[anchor_cat]
        used = used_words.setdefault(anchor_cat, set())
        if anchor_txt:
            w = anchor_txt
        else:
            w = _pick_word_avoid_dup(words, used)
        used.add(w)
        parts_list.append((anchor_cat, w))
        k -= 1

    for _ in range(k):
        cat = _pick_category(names, correlation, category_order)
        words = categories[cat]
        used = used_words.setdefault(cat, set())
        w = _pick_word_avoid_dup(words, used)
        used.add(w)
        parts_list.append((cat, w))

    summary = " × ".join(f"{a}:{b}" for a, b in parts_list)
    mode = (
        "随机2–4词"
        if combo_mode == "random"
        else f"{combo_mode}词"
    )
    anchor_note = ""
    if anchor_cat and anchor_cat in _non_empty_categories(categories):
        anchor_note = f" · 锚:{anchor_cat}"
        if anchor_txt:
            anchor_note += f"「{anchor_txt[:16]}」" if len(anchor_txt) > 16 else f"「{anchor_txt}」"
    corr_note = f" · 关联{correlation:.0%}"
    mode_label = f"{mode}（维度可重复）{corr_note}{anchor_note}"
    return {
        "parts": parts_list,
        "summary": summary,
        "word_count": len(parts_list),
        "combo_mode": mode_label,
    }
