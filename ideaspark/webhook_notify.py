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
                return True, f"HTTP {code} · 响应正文：{text}"
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
