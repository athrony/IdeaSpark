"""默认概念分类与用户持久化扩展（兼容原 word_bank.json 结构）。"""

from __future__ import annotations

import json
import re
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


def parse_bulk_words(text: str, *, max_word_len: int = 80) -> list[str]:
    """从粘贴文本解析词列表：换行、中英文逗号、顿号、分号分隔，去重保序。"""
    if not (text or "").strip():
        return []
    parts = re.split(r"[\n\r,，、；;|]+", text.strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        w = p.strip()
        if not w or len(w) > max_word_len:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def bulk_add_words(categories: dict[str, list[str]], category: str, text: str) -> dict[str, list[str]]:
    """将批量文本合并到指定维度（去重）。"""
    words = parse_bulk_words(text)
    if not words:
        return deepcopy(categories)
    out = deepcopy(categories)
    if category not in out:
        out[category] = []
    seen = set(out[category])
    for w in words:
        if w not in seen:
            out[category].append(w)
            seen.add(w)
    return out


def normalize_import_payload(data: Any) -> dict[str, list[str]]:
    """解析上传 JSON：支持 {\"categories\":{...}} 或平铺 {维度: [词,...]}。"""
    if not isinstance(data, dict):
        return {}
    root = data.get("categories") if "categories" in data else data
    if not isinstance(root, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in root.items():
        if not isinstance(v, list):
            continue
        key = str(k).strip()
        if not key:
            continue
        words = [str(x).strip() for x in v if str(x).strip()]
        if words:
            out[key] = words
    return out


def merge_categories_patch(
    categories: dict[str, list[str]],
    patch: dict[str, Any],
) -> dict[str, list[str]]:
    """
    合并多维度补丁，如 {\"技术\": [\"a\",\"b\"], \"行业\": [\"c\"]}。
    用于 JSON 文件导入。
    """
    out = deepcopy(categories)
    if not isinstance(patch, dict):
        return out
    for cat, words in patch.items():
        cat = str(cat).strip()
        if not cat or not isinstance(words, list):
            continue
        if cat not in out:
            out[cat] = []
        seen = set(out[cat])
        for w in words:
            w = str(w).strip()
            if not w or w in seen:
                continue
            out[cat].append(w)
            seen.add(w)
    return out
