"""Gemini or OpenAI evaluation: scores + short business draft."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import env_str


SYSTEM_PROMPT = """你是资深产品与战略顾问。用户会提供一个「创意配方」：由若干标签组合而成。
请严格用 JSON 回复，不要 Markdown 代码块，不要多余文字。字段如下：
{
  "market_potential": 1-10 的整数,
  "technical_feasibility": 1-10 的整数,
  "innovation_breakthrough": 1-10 的整数,
  "business_draft": "200字以内的商业初稿（中文）"
}
三个维度：市场潜力、技术可行性、创新突破点。分数要诚实、可对比。"""


@dataclass
class EvaluationResult:
    market_potential: int
    technical_feasibility: int
    innovation_breakthrough: int
    business_draft: str
    raw_text: str

    @property
    def average_score(self) -> float:
        return (
            self.market_potential
            + self.technical_feasibility
            + self.innovation_breakthrough
        ) / 3.0


def _clamp_int(v: Any, default: int = 5) -> int:
    try:
        n = int(float(v))
        return max(1, min(10, n))
    except (TypeError, ValueError):
        return default


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip markdown fences if model added them
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def parse_evaluation(text: str) -> EvaluationResult:
    data = _parse_json_loose(text)
    return EvaluationResult(
        market_potential=_clamp_int(data.get("market_potential")),
        technical_feasibility=_clamp_int(data.get("technical_feasibility")),
        innovation_breakthrough=_clamp_int(data.get("innovation_breakthrough")),
        business_draft=str(data.get("business_draft", "")).strip() or "（暂无初稿）",
        raw_text=text,
    )


def evaluate_with_gemini(recipe_summary: str) -> EvaluationResult:
    import google.generativeai as genai

    key = env_str("GOOGLE_API_KEY")
    if not key:
        raise ValueError("未设置 GOOGLE_API_KEY，请在环境变量或 .env 中配置。")

    genai.configure(api_key=key)
    model_name = env_str("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(
        model_name,
        system_instruction=SYSTEM_PROMPT,
    )
    user = f"创意配方：{recipe_summary}"
    resp = model.generate_content(user)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini 返回为空")
    return parse_evaluation(text)


def _normalize_relay_base_url(url: str) -> str:
    """OpenAI SDK 需要 base_url 以 /v1 结尾（不含具体路径）。"""
    u = url.strip().rstrip("/")
    if not u.endswith("/v1"):
        u = u + "/v1"
    return u


def evaluate_with_gemini_relay(recipe_summary: str) -> EvaluationResult:
    """
    中转站：通常为 OpenAI Chat Completions 兼容接口。
    文档示例：魔芋 AI — http://101.200.167.88:8001/#text-gemini
    环境变量：GEMINI_RELAY_BASE_URL、GEMINI_RELAY_API_KEY（或回退 GOOGLE_API_KEY）、GEMINI_RELAY_MODEL。
    """
    from openai import OpenAI

    base = env_str("GEMINI_RELAY_BASE_URL")
    if not base:
        raise ValueError(
            "中转模式需要 GEMINI_RELAY_BASE_URL（多为 http(s)://主机:端口/v1，详见中转商文档）。"
        )
    base = _normalize_relay_base_url(base)
    key = env_str("GEMINI_RELAY_API_KEY") or env_str("GOOGLE_API_KEY")
    if not key:
        raise ValueError("请设置 GEMINI_RELAY_API_KEY，或在未单独配置时填写 GOOGLE_API_KEY。")

    model = env_str("GEMINI_RELAY_MODEL", "Gemini 3.1 Flash-Lite")
    client = OpenAI(api_key=key, base_url=base)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"创意配方：{recipe_summary}"},
        ],
        temperature=0.6,
    )
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("中转 API 返回为空")
    return parse_evaluation(text)


def evaluate_with_openai(recipe_summary: str) -> EvaluationResult:
    from openai import OpenAI

    key = env_str("OPENAI_API_KEY")
    if not key:
        raise ValueError("未设置 OPENAI_API_KEY，请在环境变量或 .env 中配置。")

    client = OpenAI(api_key=key)
    model = env_str("OPENAI_MODEL", "gpt-4o-mini")
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"创意配方：{recipe_summary}"},
        ],
        temperature=0.6,
    )
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI 返回为空")
    return parse_evaluation(text)


def evaluate(recipe_summary: str, provider: str) -> EvaluationResult:
    p = (provider or "gemini").lower().strip()
    if p == "openai":
        return evaluate_with_openai(recipe_summary)
    if p in ("relay", "gemini_relay", "gemini-relay", "中转"):
        return evaluate_with_gemini_relay(recipe_summary)
    return evaluate_with_gemini(recipe_summary)
