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
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            return True, f"HTTP {code}"
    except HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
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
