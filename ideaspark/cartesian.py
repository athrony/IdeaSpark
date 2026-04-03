"""笛卡尔积全空间 + 随机种子抽样（超大空间时不建全表）。"""

from __future__ import annotations

import itertools
import math
import random
from typing import Any

from .combinator import Recipe


def _recipe_from_tuple(
    dimensions: list[str], values: tuple[str, ...], combo_label: str
) -> Recipe:
    parts = [(dimensions[i], values[i]) for i in range(len(dimensions))]
    summary = " × ".join(f"{a}:{b}" for a, b in parts)
    return {
        "parts": parts,
        "summary": summary,
        "word_count": len(parts),
        "combo_mode": combo_label,
    }


def sample_cartesian_recipes(
    categories: dict[str, list[str]],
    dimensions: list[str],
    max_words_per_dim: int,
    n_samples: int,
    seed: int,
    *,
    combo_label: str = "笛卡尔积抽样",
) -> list[Recipe]:
    """
    对每个选定维度截取至多 max_words_per_dim 个词（不放回抽样），
    在笛卡尔积上按 seed 随机抽取 n_samples 条（不重复；若空间不足则返回全部）。
    """
    rng = random.Random(seed)
    pools: list[list[str]] = []
    dims_ok: list[str] = []
    for d in dimensions:
        words = [w for w in categories.get(d, []) if w.strip()]
        if not words:
            continue
        take = min(max_words_per_dim, len(words))
        pools.append(rng.sample(words, take))
        dims_ok.append(d)

    if not pools:
        return []

    sizes = [len(p) for p in pools]
    total = math.prod(sizes)

    # 空间可控：枚举再洗牌抽样
    if total <= 2_000_000:
        space = list(itertools.product(*pools))
        rng.shuffle(space)
        picks = space[: min(n_samples, len(space))]
    else:
        # 超大空间：随机元组 + 去重
        seen: set[tuple[str, ...]] = set()
        picks = []
        attempts = 0
        max_attempts = max(n_samples * 80, 10_000)
        while len(picks) < n_samples and attempts < max_attempts:
            attempts += 1
            t = tuple(rng.choice(p) for p in pools)
            if t in seen:
                continue
            seen.add(t)
            picks.append(t)

    return [_recipe_from_tuple(dims_ok, t, combo_label) for t in picks]
