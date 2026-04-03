"""Persist high-quality ideas to Markdown and SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import IDEAS_MD_DIR, SQLITE_PATH, ensure_dirs


def _conn() -> sqlite3.Connection:
    ensure_dirs()
    c = sqlite3.connect(SQLITE_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    ensure_dirs()
    with _conn() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                recipe_summary TEXT NOT NULL,
                recipe_json TEXT NOT NULL,
                market_potential INTEGER NOT NULL,
                technical_feasibility INTEGER NOT NULL,
                innovation_breakthrough INTEGER NOT NULL,
                business_draft TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        db.commit()


def save_to_sqlite(
    recipe_summary: str,
    recipe_parts: dict[str, str],
    ev: dict[str, Any],
    source: str = "ideaspark",
) -> int:
    import json

    init_db()
    created = datetime.now().isoformat(timespec="seconds")
    payload = json.dumps(recipe_parts, ensure_ascii=False)
    with _conn() as db:
        cur = db.execute(
            """
            INSERT INTO ideas (
                created_at, recipe_summary, recipe_json,
                market_potential, technical_feasibility, innovation_breakthrough,
                business_draft, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created,
                recipe_summary,
                payload,
                int(ev["market_potential"]),
                int(ev["technical_feasibility"]),
                int(ev["innovation_breakthrough"]),
                str(ev["business_draft"]),
                source,
            ),
        )
        db.commit()
        return int(cur.lastrowid or 0)


def save_to_markdown(
    recipe_summary: str,
    recipe_parts: dict[str, str],
    ev: dict[str, Any],
    filename_prefix: str = "idea",
) -> Path:
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = IDEAS_MD_DIR / f"{filename_prefix}_{ts}.md"
    lines = [
        f"# IdeaSpark 创意存档",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 配方：{recipe_summary}",
        "",
        "## 维度评分",
        "",
        f"| 维度 | 分数 |",
        f"|------|------|",
        f"| 市场潜力 | {ev['market_potential']} |",
        f"| 技术可行性 | {ev['technical_feasibility']} |",
        f"| 创新突破点 | {ev['innovation_breakthrough']} |",
        "",
        "## 商业初稿",
        "",
        str(ev["business_draft"]),
        "",
        "## 配方明细",
        "",
    ]
    for k, v in recipe_parts.items():
        lines.append(f"- **{k}**：{v}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def list_recent_sqlite(limit: int = 20) -> list[sqlite3.Row]:
    init_db()
    with _conn() as db:
        return list(
            db.execute(
                "SELECT * FROM ideas ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )
