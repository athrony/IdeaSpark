"""合并核心、文学艺术、想象力扩展与十轮增量，供 `word_bank` 加载为默认词库。"""

from __future__ import annotations

from .lexicon_art_lit import ART_LIT_LEXICON
from .lexicon_core import CORE_LEXICON
from .lexicon_imagination import NEW_DIMENSIONS, TEN_ROUND_BOOSTS


def _dedupe_lexicon(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, lst in raw.items():
        seen: set[str] = set()
        nl: list[str] = []
        for x in lst:
            s = str(x).strip()
            if s and s not in seen:
                seen.add(s)
                nl.append(s)
        out[k] = nl
    return out


def _build_lexicon() -> dict[str, list[str]]:
    base: dict[str, list[str]] = {
        **CORE_LEXICON,
        **ART_LIT_LEXICON,
        **NEW_DIMENSIONS,
    }
    for rd in TEN_ROUND_BOOSTS:
        for cat, words in rd.items():
            base.setdefault(cat, [])
            base[cat].extend(words)
    return _dedupe_lexicon(base)


# 原 10 类 + 8 个想象力维度；并含十轮主题增量（去重后合并）
LEXICON: dict[str, list[str]] = _build_lexicon()
