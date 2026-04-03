"""Paths and environment-driven configuration."""

from __future__ import annotations

import os
from pathlib import Path

# Project root: parent of package
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
IDEAS_MD_DIR = ROOT / "ideas_saved"
WORD_BANK_PATH = DATA_DIR / "word_bank.json"
SQLITE_PATH = DATA_DIR / "ideas.db"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IDEAS_MD_DIR.mkdir(parents=True, exist_ok=True)


def env_str(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return v.strip() if v else default


def ai_provider() -> str:
    return env_str("AI_PROVIDER", "gemini").lower()
