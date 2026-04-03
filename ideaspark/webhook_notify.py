"""通用 Webhook POST（JSON），用于推送到自建服务或群机器人网关。"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 企业微信 text.content 上限 2048 字节；JSON 包装后略超，单条内容留余量
WECOM_TEXT_MAX_BYTES = 1900


def post_json_webhook(url: str, payload: dict[str, Any], timeout: float = 60.0) -> tuple[bool, str]:
    if not (url or "").strip():
        return False, "URL 为空"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url.strip(),
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "IdeaSpark/1.0 (+https://github.com/athrony/IdeaSpark)",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace").strip()
            if len(text) > 600:
                text = text[:600] + "…"
            # 200 只表示「对方 HTTP 层收下了请求」；飞书/企微/钉钉机器人往往要求固定 JSON 字段，
            # 若响应体为 {"code":2,"msg":"...feishu..."} 等，说明业务层未真正发到群里。
            if text:
                # 企业微信：HTTP 200 仍可能 body 里 errcode!=0（业务失败）
                try:
                    j = json.loads(text)
                    ec = j.get("errcode")
                    if ec is not None and int(ec) != 0:
                        return False, f"HTTP {code} · 企业微信/兼容接口返回失败：{text[:800]}"
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                return True, f"HTTP {code} · 响应正文：{text[:800]}"
            return (
                True,
                f"HTTP {code} · 响应体为空。"
                "若群里仍无消息：多数群机器人不识别 IdeaSpark 的通用 JSON，"
                "需用自建服务/n8n/云函数把 payload 转成该平台要求的格式后再 POST。",
            )
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        tail = f" · {err_body}" if err_body else ""
        return False, f"HTTP {e.code}: {e.reason}{tail}"
    except URLError as e:
        return False, str(e.reason or e)
    except Exception as e:
        return False, str(e)


def post_json_webhook_sequence(
    url: str,
    payloads: list[dict[str, Any]],
    *,
    timeout: float = 60.0,
    pause_sec: float = 0.35,
) -> tuple[bool, str]:
    """顺序发送多条 JSON（企微长文拆条），任一条失败则中止。"""
    if not payloads:
        return True, "无内容，未发送"
    lines: list[str] = []
    for i, p in enumerate(payloads, 1):
        ok, msg = post_json_webhook(url, p, timeout=timeout)
        lines.append(f"第 {i}/{len(payloads)} 条：{msg}")
        if not ok:
            return False, "\n".join(lines)
        if i < len(payloads) and pause_sec > 0:
            time.sleep(pause_sec)
    return True, "\n".join(lines)


def build_batch_payload(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
) -> dict[str, Any]:
    return {
        "source": "IdeaSpark",
        "event": "batch_review",
        "title": title,
        "rounds": rounds,
        "generated_total": generated,
        "kept_count": len(kept),
        "items": kept,
    }


def _truncate_utf8(s: str, max_bytes: int) -> str:
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    while s and len(s.encode("utf-8")) > max_bytes:
        s = s[:-1]
    return s + "\n…(已截断)"


def _utf8_prefix_len(rest: str, max_bytes: int) -> str:
    """取 rest 的前缀，UTF-8 字节数不超过 max_bytes，尽量在换行处断开。"""
    if not rest or max_bytes <= 0:
        return ""
    if len(rest.encode("utf-8")) <= max_bytes:
        return rest
    lo, hi = 0, len(rest)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(rest[:mid].encode("utf-8")) <= max_bytes:
            lo = mid
        else:
            hi = mid - 1
    cut = rest[:lo]
    if not cut:
        return rest.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    nl = cut.rfind("\n")
    if nl > 0 and nl >= max(1, lo // 3):
        return cut[: nl + 1]
    return cut


def _split_utf8_chunks(s: str, max_bytes: int) -> list[str]:
    """将长字符串拆成多段，每段不超过 max_bytes（UTF-8）。"""
    s = s.strip("\n")
    if not s:
        return [""]
    out: list[str] = []
    pos = 0
    while pos < len(s):
        chunk = _utf8_prefix_len(s[pos:], max_bytes)
        if not chunk:
            break
        out.append(chunk.rstrip("\n"))
        pos += len(chunk)
    return [x for x in out if x]


def _build_wecom_plain_body(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
) -> str:
    lines: list[str] = [
        f"【{title}】",
        f"轮次 {rounds} · 总生成 {generated} · 保留 {len(kept)} 条",
        "──────────",
    ]
    if not kept:
        lines.append("（本轮无筛选结果）")
    else:
        for i, x in enumerate(kept, 1):
            label = (x.get("optimized_name") or x.get("nouns") or "").strip() or (
                str(x.get("summary", ""))[:48]
            )
            tier = str(x.get("tier", ""))
            avg = x.get("avg", "")
            did = str(x.get("display_id", x.get("id", i)))
            buf = f"{i}. [{did}] {tier} · {label} · 均分{avg}"
            c = (x.get("comment") or "").strip()
            if c:
                buf += f"\n  {c[:200]}"
            lines.append(buf)
    return "\n".join(lines)


def build_wecom_text_payloads(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
    max_bytes: int = WECOM_TEXT_MAX_BYTES,
) -> list[dict[str, Any]]:
    """
    企业微信群机器人：1 条或多条 msgtype=text。
    超长时拆成多条 POST，避免单条 2048 字节截断。
    """
    plain = _build_wecom_plain_body(kept, title=title, rounds=rounds, generated=generated)
    chunks = _split_utf8_chunks(plain, max_bytes)
    if not chunks:
        chunks = ["（空）"]
    total = len(chunks)
    out: list[dict[str, Any]] = []
    for i, ch in enumerate(chunks, 1):
        prefix = f"（{i}/{total}）\n" if total > 1 else ""
        content = prefix + ch
        content = _truncate_utf8(content, 2030)
        out.append({"msgtype": "text", "text": {"content": content}})
    return out


def build_webhook_payloads(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
    format: str = "ideaspark",
) -> list[dict[str, Any]]:
    """返回待 POST 的 JSON 列表；企微可能多条，通用 JSON 仅 1 条。"""
    fmt = (format or "ideaspark").strip().lower()
    if fmt in ("wecom", "wecom_text", "workweixin", "wxwork", "qywx"):
        return build_wecom_text_payloads(kept, title=title, rounds=rounds, generated=generated)
    return [build_batch_payload(kept, title=title, rounds=rounds, generated=generated)]


