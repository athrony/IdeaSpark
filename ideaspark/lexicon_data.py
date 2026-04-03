"""合并「核心四维」与「文学/艺术/叙事」扩展维度，供 `word_bank` 加载为默认词库。"""

from __future__ import annotations

from .lexicon_art_lit import ART_LIT_LEXICON
from .lexicon_core import CORE_LEXICON

# 共 10 类：技术、行业、人群、心理需求 + 叙事/文体/意象/媒介/美学/互文
LEXICON: dict[str, list[str]] = {**CORE_LEXICON, **ART_LIT_LEXICON}
