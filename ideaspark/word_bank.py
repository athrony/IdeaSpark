"""Preset word categories and persistent user vocabulary."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import WORD_BANK_PATH, ensure_dirs

# Keys must match UI labels (Chinese) for display consistency
DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "技术": [
        "区块链",
        "边缘计算",
        "大语言模型",
        "计算机视觉",
        "物联网",
        "5G/6G",
        "量子计算",
        "数字孪生",
        "联邦学习",
        "RAG 检索增强",
    ],
    "行业": [
        "医疗健康",
        "教育培训",
        "金融科技",
        "零售电商",
        "智能制造",
        "物流供应链",
        "文娱传媒",
        "农业食品",
        "能源环保",
        "房地产",
    ],
    "人群": [
        "Z 世代",
        "银发族",
        "职场新人",
        "自由职业者",
        "小微企业主",
        "一线城市白领",
        "下沉市场用户",
        "跨境从业者",
        "残障人士",
        "亲子家庭",
    ],
    "心理需求": [
        "省时省力",
        "社交认同",
        "安全感",
        "自我实现",
        "性价比",
        "个性化表达",
        "治愈与放松",
        "掌控感",
        "好奇心",
        "归属感",
    ],
}


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
