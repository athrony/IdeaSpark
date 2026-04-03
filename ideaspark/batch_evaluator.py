"""省 Token 的批量评审：一次请求多行「编号|摘要」，返回紧凑 JSON。"""

from __future__ import annotations

from typing import Any

from .ai_evaluator import _normalize_relay_base_url
from .ai_evaluator import _parse_json_loose
from .config import env_str

# 输出用短字段名 c/tier，减少生成侧 token
BATCH_SYSTEM_PROMPT = """你是创意配方批量筛选员。输入格式：若干行「编号|摘要」，编号从1连续递增。
任务：
1) 对明显无厘头、纯词汇堆砌、无语境价值的配方，tier 标为 drop（不在输出里写长理由）。
2) 对其余配方给 tier：weak（略牵强）/ ok（可讨论）/ good（有趣或有落地感），并给 mp/tf/ib 三个 1-10 整数与极短点评 c（≤24字）。
3) 只输出一个 JSON 对象，不要 markdown 代码块，不要多余文字。结构：
{"items":[{"id":1,"tier":"drop|weak|ok|good","mp":0,"tf":0,"ib":0,"c":""}]}
tier=drop 时 mp/tf/ib 填 0，c 可空。"""


def _build_batch_user_text(recipes: list[dict], start_id: int = 1) -> str:
    lines = []
    for i, r in enumerate(recipes):
        sid = start_id + i
        lines.append(f"{sid}|{r.get('summary', '')}")
    return f"共{len(recipes)}条：\n" + "\n".join(lines)


def _chat_completion_batch(user_text: str, provider: str) -> str:
    p = (provider or "gemini").lower().strip()
    if p in ("openai", "relay", "gemini_relay", "gemini-relay", "中转"):
        from openai import OpenAI

        if p == "openai":
            key = env_str("OPENAI_API_KEY")
            if not key:
                raise ValueError("未设置 OPENAI_API_KEY")
            client = OpenAI(api_key=key)
            model = env_str("OPENAI_MODEL", "gpt-4o-mini")
        else:
            base = env_str("GEMINI_RELAY_BASE_URL")
            if not base:
                raise ValueError("中转模式需要 GEMINI_RELAY_BASE_URL")
            base = _normalize_relay_base_url(base)
            key = env_str("GEMINI_RELAY_API_KEY") or env_str("GOOGLE_API_KEY")
            if not key:
                raise ValueError("请设置 GEMINI_RELAY_API_KEY 或 GOOGLE_API_KEY")
            client = OpenAI(api_key=key, base_url=base)
            model = env_str("GEMINI_RELAY_MODEL", "Gemini 3.1 Flash-Lite")

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.25,
        )
        return (completion.choices[0].message.content or "").strip()

    import google.generativeai as genai

    key = env_str("GOOGLE_API_KEY")
    if not key:
        raise ValueError("未设置 GOOGLE_API_KEY")
    genai.configure(api_key=key)
    model_name = env_str("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(
        model_name,
        system_instruction=BATCH_SYSTEM_PROMPT,
    )
    resp = model.generate_content(user_text)
    return (resp.text or "").strip()


def parse_batch_items(text: str) -> list[dict[str, Any]]:
    data = _parse_json_loose(text)
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            rid = int(it.get("id", 0))
        except (TypeError, ValueError):
            continue
        tier = str(it.get("tier", "ok")).lower().strip()
        out.append(
            {
                "id": rid,
                "tier": tier,
                "mp": _clamp_score(it.get("mp")),
                "tf": _clamp_score(it.get("tf")),
                "ib": _clamp_score(it.get("ib")),
                "c": str(it.get("c", "")).strip()[:200],
            }
        )
    return out


def _clamp_score(v: Any) -> int:
    try:
        n = int(float(v))
        return max(0, min(10, n))
    except (TypeError, ValueError):
        return 0


def evaluate_batch(
    recipes: list[dict],
    provider: str,
    *,
    chunk_size: int = 36,
) -> tuple[list[dict[str, Any]], str]:
    """
    返回 (解析后的 items 列表, 原始拼接文本)。
    超长时按 chunk 切块多次请求，id 仍用全局编号。
    """
    if not recipes:
        return [], ""

    raw_chunks: list[str] = []
    all_items: list[dict[str, Any]] = []

    for start in range(0, len(recipes), chunk_size):
        chunk = recipes[start : start + chunk_size]
        start_id = start + 1
        user_text = _build_batch_user_text(chunk, start_id=start_id)
        raw = _chat_completion_batch(user_text, provider)
        raw_chunks.append(raw)
        items = parse_batch_items(raw)
        all_items.extend(items)

    return all_items, "\n---\n".join(raw_chunks)


def merge_kept_results(
    recipes: list[dict],
    items: list[dict[str, Any]],
    *,
    min_avg: float,
    exclude_weak: bool,
) -> list[dict[str, Any]]:
    """筛掉 drop；可选筛 weak；平均分未达阈值则丢弃（tier 为 ok/good 但全 0 分仍保留一条以免模型漏打分）。"""
    by_line = {i + 1: r for i, r in enumerate(recipes)}
    seen_ids: set[int] = set()
    out: list[dict[str, Any]] = []

    for it in items:
        rid = int(it.get("id", 0))
        if rid < 1 or rid > len(recipes) or rid in seen_ids:
            continue
        seen_ids.add(rid)
        tier = str(it.get("tier", "")).lower()
        if tier == "drop":
            continue
        if exclude_weak and tier == "weak":
            continue
        mp, tf, ib = it.get("mp", 0), it.get("tf", 0), it.get("ib", 0)
        ssum = mp + tf + ib
        avg = ssum / 3.0 if ssum > 0 else 0.0
        if ssum == 0 and tier in ("ok", "good"):
            keep = True
        else:
            keep = avg >= min_avg
        if not keep:
            continue
        out.append(
            {
                "id": rid,
                "summary": by_line[rid].get("summary", ""),
                "parts": by_line[rid].get("parts", []),
                "tier": tier,
                "mp": mp,
                "tf": tf,
                "ib": ib,
                "avg": round(avg, 2),
                "comment": it.get("c", ""),
            }
        )
    return out
