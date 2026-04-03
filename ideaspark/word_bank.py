"""Preset word categories and persistent user vocabulary."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import WORD_BANK_PATH, ensure_dirs
from .lexicon_data import LEXICON

# 与 lexicon_data 同步；运行时与用户 JSON 合并
DEFAULT_CATEGORIES: dict[str, list[str]] = {k: list(v) for k, v in LEXICON.items()}


def _load_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_categories() -> dict[str, list[str]]:
    """Merge defaults with saved `categories` from disk."""
    ensure_dirs()
    data = _load_file(WORD_BANK_PATH)
    merged = deepcopy(DEFAULT_CATEGORIES)
    if not data or "categories" not in data:
        return merged
    saved = data["categories"]
    if not isinstance(saved, dict):
        return merged
    for key, words in saved.items():
        if not isinstance(words, list):
            continue
        clean = [str(w).strip() for w in words if str(w).strip()]
        if key in merged:
            seen = set(merged[key])
            for w in clean:
                if w not in seen:
                    merged[key].append(w)
                    seen.add(w)
        else:
            merged[key] = clean
    return merged


def save_categories(categories: dict[str, list[str]]) -> None:
    ensure_dirs()
    payload = {"categories": categories}
    with open(WORD_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def add_word(categories: dict[str, list[str]], category: str, word: str) -> dict[str, list[str]]:
    w = word.strip()
    if not w:
        return categories
    out = deepcopy(categories)
    if category not in out:
        out[category] = []
    if w not in out[category]:
        out[category].append(w)
    return out
