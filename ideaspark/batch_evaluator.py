"""省 Token 的批量评审：一次请求多行「编号|摘要」，返回紧凑 JSON。"""

from __future__ import annotations

import time
from typing import Any

from .ai_evaluator import _normalize_relay_base_url
from .ai_evaluator import _parse_json_loose
from .combinator import recipe_nouns_join
from .config import env_str

# 输出用短字段名 c/tier，减少生成侧 token
BATCH_SYSTEM_PROMPT = """你是创意配方批量筛选员。输入格式：若干行「编号|摘要」，编号从1连续递增。
任务：
1) 对明显无厘头、纯词汇堆砌、无语境价值的配方，tier 标为 drop（不在输出里写长理由）。
2) 对其余配方给 tier：weak（略牵强）/ ok（可讨论）/ good（有趣或有落地感），并给 mp/tf/ib 三个 1-10 整数与极短点评 c（≤24字）。
3) 每项必须给 nm：由该条摘要提炼的「优化创意名」6-14 字，顺口好记，勿简单堆砌原词。
4) 只输出一个 JSON 对象，不要 markdown 代码块，不要多余文字。结构：
{"items":[{"id":1,"tier":"drop|weak|ok|good","mp":0,"tf":0,"ib":0,"c":"","nm":""}]}
tier=drop 时 mp/tf/ib 填 0，c、nm 可空。"""


def _openai_chat_create_with_retry(client: Any, **kwargs: Any) -> Any:
    """
    批量评审单次请求：对 5xx / 超时 / 连接失败 / 429 做有限重试；
    其它错误转为简短 ValueError，避免 Streamlit Cloud 过度脱敏后用户完全看不到原因。
    """
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    max_attempts = 4
    base_delay = 1.25

    for attempt in range(max_attempts):
        try:
            return client.chat.completions.create(**kwargs)
        except APITimeoutError:
            if attempt >= max_attempts - 1:
                raise ValueError(
                    "请求超时，已多次重试仍失败。请稍后重试或减小「每批评审条数」。"
                ) from None
        except APIConnectionError:
            if attempt >= max_attempts - 1:
                raise ValueError(
                    "无法连接中转或模型接口。请检查基础地址、网络或稍后重试。"
                ) from None
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            # 先处理 4xx（不含 429，否则会与限流重试逻辑冲突）
            if code is not None and code < 500 and code != 429:
                if code == 401:
                    msg = "密钥无效或未授权（状态 401）。请检查侧栏或 Secrets 中的密钥。"
                elif code == 404:
                    msg = (
                        "地址或模型不存在（状态 404）。请确认基础地址含 /v1，且模型名与中转商文档一致。"
                    )
                elif code == 400:
                    msg = (
                        "请求被拒绝（状态 400）。可尝试减小「每批评审条数」或更换模型名。"
                    )
                else:
                    msg = f"接口返回错误（状态 {code}）。"
                raise ValueError(msg) from None
            if code == 429:
                if attempt >= max_attempts - 1:
                    raise ValueError(
                        "触发限流（状态 429），已重试仍失败。请稍后再试或减小批量。"
                    ) from None
            else:
                # 5xx 或 status 为空
                if attempt >= max_attempts - 1:
                    raise ValueError(
                        "中转返回服务端错误（状态 5xx），已重试仍失败。"
                        "多为对端短暂故障或负载高，请稍后重试、减小每批条数，或联系中转商。"
                    ) from None
        except Exception as e:
            # 兼容不同版本 SDK 抛出的 InternalServerError 等
            name = type(e).__name__
            if name in ("InternalServerError", "InternalError") or "ServerError" in name:
                if attempt >= max_attempts - 1:
                    raise ValueError(
                        "中转返回服务器内部错误，已多次重试仍失败。请稍后重试或减小批量。"
                    ) from None
            else:
                raise ValueError(
                    f"调用模型失败（{name}）。请检查配置与网络后重试。"
                ) from None

        time.sleep(base_delay * (2**attempt))

    raise ValueError("批量评审请求失败（未知原因）。") from None


def _build_batch_user_text(recipes: list[dict], start_id: int = 1) -> str:
    lines = []
    for i, r in enumerate(recipes):
        sid = start_id + i
        lines.append(f"{sid}|{r.get('summary', '')}")
    return f"共{len(recipes)}条：\n" + "\n".join(lines)


def _chat_completion_batch(
    user_text: str,
    provider: str,
    *,
    relay_base_url: str | None = None,
    relay_api_key: str | None = None,
    relay_model: str | None = None,
    relay_protocol: str | None = None,
) -> str:
    p = (provider or "gemini").lower().strip()
    if p in ("openai", "relay", "gemini_relay", "gemini-relay", "中转"):
        from openai import OpenAI

        if p == "openai":
            key = env_str("OPENAI_API_KEY")
            if not key:
                raise ValueError("未设置 OPENAI_API_KEY")
            client = OpenAI(api_key=key, timeout=180.0)
            model = env_str("OPENAI_MODEL", "gpt-4o-mini")
            completion = _openai_chat_create_with_retry(
                client,
                model=model,
                messages=[
                    {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.25,
            )
            return (completion.choices[0].message.content or "").strip()

        base = (relay_base_url or env_str("GEMINI_RELAY_BASE_URL")).strip()
        if not base:
            raise ValueError(
                "中转模式需要填写「中转 Base URL」或在环境变量中设置 GEMINI_RELAY_BASE_URL。"
            )
        proto = (relay_protocol or env_str("GEMINI_RELAY_PROTOCOL", "openai")).lower().strip()
        key = (relay_api_key or env_str("GEMINI_RELAY_API_KEY") or env_str("GOOGLE_API_KEY")).strip()
        if not key:
            raise ValueError("请设置中转 API Key，或填写 GOOGLE_API_KEY 作为备用。")
        _def_m = (
            "gemini-2.0-flash"
            if proto in ("gemini_rest", "gemini", "native", "rest", "generatecontent")
            else "Gemini 3.1 Flash-Lite"
        )
        model = (relay_model or env_str("GEMINI_RELAY_MODEL", _def_m)).strip()

        if proto in ("gemini_rest", "gemini", "native", "rest", "generatecontent"):
            from .gemini_relay_rest import generate_content_rest, normalize_gemini_relay_origin

            origin = normalize_gemini_relay_origin(base)
            return generate_content_rest(
                origin=origin,
                api_key=key,
                model=model,
                system_instruction=BATCH_SYSTEM_PROMPT,
                user_text=user_text,
                temperature=0.25,
            )

        base = _normalize_relay_base_url(base)
        client = OpenAI(api_key=key, base_url=base, timeout=180.0)
        completion = _openai_chat_create_with_retry(
            client,
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
                "nm": str(it.get("nm", "")).strip()[:40],
            }
        )
    return out


def _clamp_score(v: Any) -> int:
    try:
        n = int(float(v))
        return max(0, min(10, n))
    except (TypeError, ValueError):
        return 0


def _should_bisect_chunk_on_error(msg: str) -> bool:
    """对端过载、单次过长、限流等可尝试拆半重试；客户端错误（4xx 配置问题）不拆。"""
    if not msg:
        return False
    if any(
        x in msg
        for x in ("状态 401", "状态 404", "状态 400", "密钥无效", "地址或模型不存在")
    ):
        return False
    if "5xx" in msg or "服务端" in msg or "服务器内部" in msg:
        return True
    if "状态 5" in msg:
        return True
    if "超时" in msg or "无法连接" in msg:
        return True
    if "429" in msg or "限流" in msg:
        return True
    return False


def _evaluate_chunk_with_bisect(
    chunk: list[dict],
    start_id: int,
    provider: str,
    *,
    relay_base_url: str | None,
    relay_api_key: str | None,
    relay_model: str | None,
    relay_protocol: str | None,
    depth: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    """
    单次批量请求；若返回服务端/限流/超时类 ValueError，则将当前块拆成两半递归重试（最多拆到单条）。
    """
    user_text = _build_batch_user_text(chunk, start_id=start_id)
    try:
        raw = _chat_completion_batch(
            user_text,
            provider,
            relay_base_url=relay_base_url,
            relay_api_key=relay_api_key,
            relay_model=relay_model,
            relay_protocol=relay_protocol,
        )
        return raw, parse_batch_items(raw)
    except ValueError as e:
        msg = (e.args[0] if e.args else "") or ""
        if depth >= 8 or len(chunk) <= 1 or not _should_bisect_chunk_on_error(msg):
            raise
        mid = len(chunk) // 2
        if mid < 1:
            raise
        r1, items1 = _evaluate_chunk_with_bisect(
            chunk[:mid],
            start_id,
            provider,
            relay_base_url=relay_base_url,
            relay_api_key=relay_api_key,
            relay_model=relay_model,
            relay_protocol=relay_protocol,
            depth=depth + 1,
        )
        r2, items2 = _evaluate_chunk_with_bisect(
            chunk[mid:],
            start_id + mid,
            provider,
            relay_base_url=relay_base_url,
            relay_api_key=relay_api_key,
            relay_model=relay_model,
            relay_protocol=relay_protocol,
            depth=depth + 1,
        )
        return r1 + "\n---\n" + r2, items1 + items2


def evaluate_batch(
    recipes: list[dict],
    provider: str,
    *,
    chunk_size: int = 36,
    relay_base_url: str | None = None,
    relay_api_key: str | None = None,
    relay_model: str | None = None,
    relay_protocol: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    返回 (解析后的 items 列表, 原始拼接文本)。
    超长时按 chunk 切块多次请求，id 仍用全局编号。
    中转模式可传入 relay_* 显式覆盖环境变量（与侧栏 session 对齐）。
    """
    if not recipes:
        return [], ""

    raw_chunks: list[str] = []
    all_items: list[dict[str, Any]] = []

    for start in range(0, len(recipes), chunk_size):
        chunk = recipes[start : start + chunk_size]
        start_id = start + 1
        raw, items = _evaluate_chunk_with_bisect(
            chunk,
            start_id,
            provider,
            relay_base_url=relay_base_url,
            relay_api_key=relay_api_key,
            relay_model=relay_model,
            relay_protocol=relay_protocol,
        )
        raw_chunks.append(raw)
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
        rec = by_line[rid]
        nouns = recipe_nouns_join(rec)
        nm = (it.get("nm") or "").strip()
        out.append(
            {
                "id": rid,
                "summary": rec.get("summary", ""),
                "parts": rec.get("parts", []),
                "nouns": nouns,
                "optimized_name": nm or nouns,
                "tier": tier,
                "mp": mp,
                "tf": tf,
                "ib": ib,
                "avg": round(avg, 2),
                "comment": it.get("c", ""),
            }
        )
    return out
