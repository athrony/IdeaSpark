"""
IdeaSpark — Streamlit entry: word banks, random recipes, AI evaluation, persistence.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Load .env from project root before other imports use os.environ
_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")


def _merge_streamlit_secrets() -> None:
    try:
        for key in (
            "OPENAI_API_KEY",
            "GOOGLE_API_KEY",
            "AI_PROVIDER",
            "GEMINI_MODEL",
            "OPENAI_MODEL",
        ):
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass


st.set_page_config(
    page_title="IdeaSpark",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)
_merge_streamlit_secrets()

from ideaspark.ai_evaluator import EvaluationResult, evaluate
from ideaspark.combinator import draw_recipe
from ideaspark.config import ROOT, ai_provider
from ideaspark.storage import init_db, list_recent_sqlite, save_to_markdown, save_to_sqlite
from ideaspark.word_bank import add_word, load_categories, save_categories


def _is_excellent(ev: EvaluationResult) -> bool:
    """Average of three dimensions strictly greater than 8."""
    return ev.average_score > 8.0


def main() -> None:
    st.title("✨ IdeaSpark")
    st.caption("创意生成引擎 · 词库随机组合 · AI 多维度评分 · 本地存档")

    if "categories" not in st.session_state:
        st.session_state.categories = load_categories()
    if "last_recipe" not in st.session_state:
        st.session_state.last_recipe = None
    if "last_eval" not in st.session_state:
        st.session_state.last_eval = None

    init_db()

    with st.sidebar:
        st.subheader("AI 设置")
        prov = st.radio(
            "API 提供商",
            options=["gemini", "openai"],
            index=0 if ai_provider() != "openai" else 1,
            horizontal=True,
        )
        os.environ["AI_PROVIDER"] = prov

        st.markdown("密钥可写在项目根目录 `.env` 或 Streamlit `secrets.toml`。")
        gk = st.text_input("Google API Key", type="password", value=os.environ.get("GOOGLE_API_KEY", ""))
        ok = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
        if gk:
            os.environ["GOOGLE_API_KEY"] = gk
        if ok:
            os.environ["OPENAI_API_KEY"] = ok

        gem_m = st.text_input(
            "Gemini 模型",
            value=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        )
        oa_m = st.text_input(
            "OpenAI 模型",
            value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )
        os.environ["GEMINI_MODEL"] = gem_m
        os.environ["OPENAI_MODEL"] = oa_m

        auto_eval = st.checkbox("生成配方后自动调用 AI 评价", value=False)

    col_main, col_side = st.columns([2, 1], gap="large")

    with col_main:
        st.subheader("词库管理")
        cats = st.session_state.categories
        tabs = st.tabs(list(cats.keys()))
        for i, name in enumerate(cats.keys()):
            with tabs[i]:
                st.write("当前词列表：")
                st.caption(" · ".join(cats[name]) if cats[name] else "（空）")
                c1, c2 = st.columns([3, 1])
                with c1:
                    new_w = st.text_input(f"添加新词 · {name}", key=f"add_{name}", placeholder="输入后点击添加")
                with c2:
                    st.write("")
                    st.write("")
                    if st.button("添加", key=f"btn_add_{name}"):
                        st.session_state.categories = add_word(
                            st.session_state.categories, name, new_w or ""
                        )
                        save_categories(st.session_state.categories)
                        st.rerun()

        st.divider()
        gen = st.button("🎲 生成创意配方", type="primary", use_container_width=True)
        if gen:
            recipe = draw_recipe(st.session_state.categories)
            st.session_state.last_recipe = recipe
            st.session_state.last_eval = None
            if auto_eval:
                try:
                    st.session_state.last_eval = evaluate(recipe["summary"], prov)
                except Exception as e:
                    st.session_state.eval_error = str(e)
            else:
                st.session_state.pop("eval_error", None)
            st.rerun()

        if st.session_state.last_recipe:
            r = st.session_state.last_recipe
            st.subheader("当前配方")
            for k, v in r["parts"].items():
                st.markdown(f"**{k}** · `{v}`")
            st.info(r["summary"])

            err = st.session_state.get("eval_error")
            if err:
                st.error(f"自动评价失败：{err}")
                st.session_state.pop("eval_error", None)

            if not auto_eval:
                if st.button("发送 AI 评价", use_container_width=True):
                    try:
                        with st.spinner("正在请求 AI…"):
                            st.session_state.last_eval = evaluate(r["summary"], prov)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    with col_side:
        st.subheader("AI 评价")
        ev = st.session_state.last_eval
        if ev:
            m1, m2, m3 = st.columns(3)
            m1.metric("市场潜力", f"{ev.market_potential}/10")
            m2.metric("技术可行性", f"{ev.technical_feasibility}/10")
            m3.metric("创新突破点", f"{ev.innovation_breakthrough}/10")
            st.caption(f"平均分：{ev.average_score:.2f}")
            st.markdown("**商业初稿**")
            st.write(ev.business_draft)

            excellent = _is_excellent(ev)
            if excellent:
                st.success("已达到「优秀」标准（三项平均分 > 8），建议存档。")
            else:
                st.info("未达「优秀」标准时仍可手动保存。")

            ev_dict = {
                "market_potential": ev.market_potential,
                "technical_feasibility": ev.technical_feasibility,
                "innovation_breakthrough": ev.innovation_breakthrough,
                "business_draft": ev.business_draft,
            }
            s1, s2 = st.columns(2)
            with s1:
                if st.button("保存到 Markdown", use_container_width=True):
                    path = save_to_markdown(
                        st.session_state.last_recipe["summary"],
                        st.session_state.last_recipe["parts"],
                        ev_dict,
                    )
                    st.toast(f"已保存：{path.relative_to(ROOT)}")
            with s2:
                if st.button("写入 SQLite", use_container_width=True):
                    rid = save_to_sqlite(
                        st.session_state.last_recipe["summary"],
                        st.session_state.last_recipe["parts"],
                        ev_dict,
                    )
                    st.toast(f"已写入数据库，id={rid}")
        else:
            st.write("生成配方并发起 AI 评价后，结果将显示在此处。")

        st.divider()
        st.subheader("最近存档（SQLite）")
        rows = list_recent_sqlite(12)
        if not rows:
            st.caption("暂无记录")
        else:
            for row in rows:
                with st.expander(f"#{row['id']} · {row['created_at'][:19]}"):
                    st.write(row["recipe_summary"])
                    st.caption(
                        f"分：{row['market_potential']} / {row['technical_feasibility']} / {row['innovation_breakthrough']}"
                    )


if __name__ == "__main__":
    main()
