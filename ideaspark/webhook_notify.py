"""通用 Webhook POST（JSON），用于推送到自建服务或群机器人网关。"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    return s + "\n…(已截断，企微 text 单条上限 2048 字节)"


def build_wecom_text_payload(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
) -> dict[str, Any]:
    """
    企业微信群机器人 Webhook：必须带 msgtype，否则 errcode=40008 invalid message type。
    文档：https://developer.work.weixin.qq.com/document/path/91770
    """
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
                buf += f"\n  {c[:120]}"
            lines.append(buf)
    body = "\n".join(lines)
    body = _truncate_utf8(body, 2040)
    return {"msgtype": "text", "text": {"content": body}}


def build_webhook_payload(
    kept: list[dict[str, Any]],
    *,
    title: str,
    rounds: int,
    generated: int,
    format: str = "ideaspark",
) -> dict[str, Any]:
    """format: ideaspark（默认）| wecom_text（企业微信群机器人文本）"""
    fmt = (format or "ideaspark").strip().lower()
    if fmt in ("wecom", "wecom_text", "workweixin", "wxwork", "qywx"):
        return build_wecom_text_payload(kept, title=title, rounds=rounds, generated=generated)
    return build_batch_payload(kept, title=title, rounds=rounds, generated=generated)
