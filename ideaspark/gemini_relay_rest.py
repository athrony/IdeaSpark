"""Gemini HTTP 中转：POST …/v1beta/models/{model}:generateContent（与 OpenAI chat/completions 不同）。"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from .config import env_str


def normalize_gemini_relay_origin(url: str) -> str:
    """
    只取站点根，例如 https://www.moyu.info。
    若粘贴完整 generateContent 地址，也会自动截成根域名。
    """
    u = (url or "").strip()
    if not u:
        raise ValueError("中转地址不能为空。")
    if "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        raise ValueError("中转地址需为完整网址，例如 https://www.moyu.info")
    return f"{p.scheme}://{p.netloc}"


def build_generate_content_url(origin: str, model: str) -> str:
    mid = quote(model.strip(), safe="")
    path = f"v1beta/models/{mid}:generateContent"
    base = origin.rstrip("/") + "/"
    return urljoin(base, path)


def _relay_auth_headers(api_key: str) -> dict[str, str]:
    style = env_str("GEMINI_RELAY_AUTH", "goog").lower()
    h: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if style in ("bearer", "token", "authorization"):
        h["Authorization"] = f"Bearer {api_key}"
    else:
        h["x-goog-api-key"] = api_key
    return h


def _parse_generate_content_json(data: dict[str, Any]) -> str:
    err = data.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message", err))
        code = err.get("code")
        raise ValueError(f"中转返回错误：{msg}" + (f"（{code}）" if code else ""))
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        fb = data.get("promptFeedback")
        if isinstance(fb, dict) and fb.get("blockReason"):
            raise ValueError(f"请求被安全策略拦截：{fb.get('blockReason')}")
        raise ValueError("中转返回无 candidates，请检查模型名与密钥。")
    parts = cands[0].get("content", {}).get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("中转返回内容为空。")
    texts: list[str] = []
    for pt in parts:
        if isinstance(pt, dict) and "text" in pt:
            texts.append(str(pt["text"]))
    return "".join(texts).strip()


def generate_content_rest(
    *,
    origin: str,
    api_key: str,
    model: str,
    system_instruction: str,
    user_text: str,
    temperature: float,
    timeout_sec: float = 180.0,
) -> str:
    """调用 Gemini 兼容的 generateContent JSON API，返回模型文本。"""
    url = build_generate_content_url(origin, model)
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": temperature},
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = _relay_auth_headers(api_key)
    max_attempts = 4
    base_delay = 1.25
    last_err: Exception | None = None

    for attempt in range(max_attempts):
        req = Request(url, data=raw, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout_sec) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                raise ValueError("中转返回非 JSON，请检查地址是否为 Gemini 兼容网关。") from None
            return _parse_generate_content_json(data)
        except HTTPError as e:
            code = int(e.code or 0)
            msg = ""
            try:
                payload = e.read().decode("utf-8", errors="replace")
                data = json.loads(payload)
                err = data.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message", ""))[:500]
            except Exception:
                pass
            if code in (401, 400, 404) or (400 <= code < 500 and code != 429):
                raise ValueError(
                    f"中转返回错误（状态 {code}）：{msg or '请检查密钥、模型名与站点根地址'}"
                ) from None
            last_err = ValueError(f"中转返回错误（状态 {code}）：{msg or '服务端异常'}")
            if code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                time.sleep(base_delay * (2**attempt))
                continue
            raise last_err from None
        except URLError as e:
            last_err = ValueError(f"网络错误：{e.reason}")
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2**attempt))
                continue
            raise last_err from None
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"解析中转响应失败：{type(e).__name__}") from None

    if last_err:
        raise last_err
    raise ValueError("中转请求失败（未知原因）。")
