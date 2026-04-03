"""
IdeaSpark — Streamlit entry: word banks, random recipes, AI evaluation, persistence.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Streamlit Cloud / Linux: ensure repo root is importable (package folder `ideaspark/`)
_ROOT = Path(__file__).resolve().parent
_root_str = str(_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")


def _merge_streamlit_secrets() -> None:
    try:
        for key in (
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
            "AI_PROVIDER",
            "GEMINI_MODEL",
            "OPENAI_MODEL",
            "GEMINI_RELAY_BASE_URL",
            "GEMINI_RELAY_API_KEY",
            "GEMINI_RELAY_MODEL",
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
from ideaspark.cartesian import sample_cartesian_recipes
from ideaspark.combinator import draw_recipe, recipe_pairs
from ideaspark.config import ROOT, ai_provider
from ideaspark.storage import init_db, list_recent_sqlite, save_to_markdown, save_to_sqlite
from ideaspark.word_bank import add_word, load_categories, save_categories


def _is_excellent(ev: EvaluationResult) -> bool:
    """Average of three dimensions strictly greater than 8."""
    return ev.average_score > 8.0


def _sync_group_boxes(keys: list[str]) -> None:
    """类别增删时同步两组拖拽容器。"""
    sig = tuple(keys)
    if st.session_state.get("_cat_sig") != sig:
        mid = (len(keys) + 1) // 2
        st.session_state.grp_boxes = [
            {"header": "组 1 · 落地/优先", "items": list(keys[:mid])},
            {"header": "组 2 · 文艺/实验", "items": list(keys[mid:])},
        ]
        st.session_state._cat_sig = sig


def _provider_radio_index() -> int:
    p = ai_provider()
    if p in ("relay", "gemini_relay", "gemini-relay"):
        return 1
    if p == "openai":
        return 2
    return 0


def _flatten_groups(boxes: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for b in boxes:
        for it in b.get("items", []):
            if it not in seen:
                seen.add(it)
                out.append(it)
    return out


def main() -> None:
    st.title("✨ IdeaSpark")
    st.caption(
        "创意生成引擎 · 锚点 / 关联度 / 维度拖拽分组 · 笛卡尔积抽样 · AI 评价 · 本地存档"
    )

    if "categories" not in st.session_state:
        st.session_state.categories = load_categories()
    if "last_recipes" not in st.session_state:
        st.session_state.last_recipes = []
    if "evaluations" not in st.session_state:
        st.session_state.evaluations = {}

    init_db()

    with st.sidebar:
        st.subheader("AI 设置")
        prov = st.radio(
            "API 提供商",
            options=["gemini", "relay", "openai"],
            index=_provider_radio_index(),
            format_func=lambda x: {
                "gemini": "Gemini 官方直连",
                "relay": "中转 API（Gemini / OpenAI 兼容）",
                "openai": "OpenAI 官方",
            }[x],
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
            "Gemini 模型（官方直连）",
            value=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            disabled=(prov != "gemini"),
        )
        oa_m = st.text_input(
            "OpenAI 模型",
            value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            disabled=(prov != "openai"),
        )
        os.environ["GEMINI_MODEL"] = gem_m
        os.environ["OPENAI_MODEL"] = oa_m

        if prov == "relay":
            st.markdown(
                "中转说明见 [魔芋 AI 文档](http://101.200.167.88:8001/#text-gemini)（一般为 OpenAI 兼容 `…/v1/chat/completions`）。"
            )
            relay_base = st.text_input(
                "中转 Base URL",
                value=os.environ.get("GEMINI_RELAY_BASE_URL", ""),
                placeholder="http://101.200.167.88:8001/v1",
                help="需包含 /v1；若只填到端口会自动补 /v1。",
            )
            relay_key = st.text_input(
                "中转 API Key",
                type="password",
                value=os.environ.get("GEMINI_RELAY_API_KEY", os.environ.get("GOOGLE_API_KEY", "")),
            )
            relay_model = st.text_input(
                "中转模型名",
                value=os.environ.get("GEMINI_RELAY_MODEL", "Gemini 3.1 Flash-Lite"),
            )
            if relay_base:
                os.environ["GEMINI_RELAY_BASE_URL"] = relay_base.strip()
            if relay_key:
                os.environ["GEMINI_RELAY_API_KEY"] = relay_key
            os.environ["GEMINI_RELAY_MODEL"] = relay_model.strip() or "Gemini 3.1 Flash-Lite"

        auto_eval = st.checkbox("生成后自动评价第 1 条", value=False)

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
        _combo_labels: dict[str, str | int] = {
            "随机 (2–4 词，维度随机)": "random",
            "2 词（两维度碰撞）": 2,
            "3 词（三维度碰撞）": 3,
            "4 词（全维度）": 4,
        }
        row1, row2 = st.columns([3, 2])
        with row1:
            combo_label = st.selectbox(
                "组合方式",
                options=list(_combo_labels.keys()),
                index=0,
                help="每一「词槽」独立随机选一类再选一词；同类可重复出现（如 技术+技术）。同一类内尽量抽不同词，词不够时才重复。",
            )
        with row2:
            batch_n = st.number_input(
                "本批生成数量",
                min_value=1,
                max_value=50,
                value=5,
                step=1,
                help="一次点击可生成多条互不相同的随机配方，便于快速浏览与筛选。",
            )
        combo_mode = _combo_labels[combo_label]

        cat_keys = list(cats.keys())
        _sync_group_boxes(cat_keys)

        st.markdown("**行业锚点 · 关联度**")
        hb1, hb2, hb3, hb4 = st.columns([1.1, 1.8, 1.6, 2.2])
        with hb1:
            gen = st.button("🎲 生成创意配方", type="primary", use_container_width=True)
        with hb2:
            anchor_word = st.text_input(
                "行业锚点（必选词）",
                key="anchor_word_input",
                placeholder="如：金融交易",
                help="指定后首槽固定为该词；可填词库外自定义词。留空则不锁定首词。",
            )
        with hb3:
            anchor_opts = ["（不使用锚点）"] + cat_keys
            _ai = 0
            if "行业" in anchor_opts:
                _ai = anchor_opts.index("行业")
            anchor_pick = st.selectbox(
                "锚点维度",
                options=anchor_opts,
                index=_ai,
                help="首槽使用的维度；与锚点词一起构成必选组合。",
            )
        with hb4:
            correlation = st.slider(
                "关联度",
                min_value=0.0,
                max_value=1.0,
                value=0.45,
                step=0.05,
                help="低：混沌狂想（全维度均匀随机）。高：商业模式（优先行业/技术/人群/心理，并按下方拖拽顺序加权）。",
            )

        with st.expander("维度分组（拖拽排序 · 可跨组拖动）", expanded=False):
            try:
                from streamlit_sortables import sort_items

                st.session_state.grp_boxes = sort_items(
                    st.session_state.grp_boxes,
                    multi_containers=True,
                )
                st.session_state.dim_order = _flatten_groups(st.session_state.grp_boxes)
            except Exception as e:
                st.warning(f"拖拽组件不可用（{e}），已回退为列表优先级。")
                st.session_state.dim_order = st.multiselect(
                    "维度优先级（靠前优先，用于高关联度加权）",
                    options=cat_keys,
                    default=st.session_state.get("dim_order") or cat_keys,
                    key="dim_order_fallback",
                )

        with st.expander("笛卡尔积 · 随机种子抽样", expanded=False):
            st.caption(
                "选定若干维度，各维截取最多 N 个词后做笛卡尔积；空间过大时以种子做随机抽样（尽量不重复）。"
            )
            cp_dims = st.multiselect(
                "参与维度（顺序保留）",
                options=cat_keys,
                default=cat_keys[: min(3, len(cat_keys))],
                key="cp_dims",
            )
            cp1, cp2, cp3, cp4 = st.columns(4)
            with cp1:
                cp_cap = st.number_input("每维最多词数", 2, 120, 18, key="cp_cap")
            with cp2:
                cp_n = st.number_input("抽样条数", 1, 500, 40, key="cp_n")
            with cp3:
                cp_seed = st.number_input("随机种子", 0, 2**31 - 1, 2026, key="cp_seed")
            with cp4:
                st.write("")
                cp_go = st.button("生成笛卡尔样本", key="cp_go")

            if cp_go:
                if len(cp_dims) < 2:
                    st.error("请至少选择 2 个维度。")
                else:
                    st.session_state.pop("pick_recipe_idx", None)
                    st.session_state.last_recipes = sample_cartesian_recipes(
                        st.session_state.categories,
                        cp_dims,
                        int(cp_cap),
                        int(cp_n),
                        int(cp_seed),
                        combo_label=f"笛卡尔·种子{cp_seed}",
                    )
                    st.session_state.evaluations = {}
                    st.session_state.pop("eval_error", None)
                    st.rerun()

        if gen:
            st.session_state.pop("pick_recipe_idx", None)
            acat = None if anchor_pick == "（不使用锚点）" else anchor_pick
            aw_raw = (anchor_word or "").strip()
            dim_order = st.session_state.get("dim_order") or cat_keys
            recipes = [
                draw_recipe(
                    st.session_state.categories,
                    combo_mode=combo_mode,
                    correlation=float(correlation),
                    anchor_category=acat,
                    anchor_word=aw_raw if aw_raw else None,
                    category_order=dim_order,
                )
                for _ in range(int(batch_n))
            ]
            st.session_state.last_recipes = recipes
            st.session_state.evaluations = {}
            if auto_eval and recipes:
                try:
                    st.session_state.evaluations[0] = evaluate(recipes[0]["summary"], prov)
                except Exception as e:
                    st.session_state.eval_error = str(e)
            else:
                st.session_state.pop("eval_error", None)
            st.rerun()

        recipes = st.session_state.last_recipes
        if recipes:
            st.subheader(f"本批配方（共 {len(recipes)} 条）")
            overview_rows = [
                {
                    "序号": i + 1,
                    "词数": r.get("word_count", len(recipe_pairs(r.get("parts")))),
                    "组合": r.get("combo_mode", ""),
                    "一行摘要": r["summary"],
                }
                for i, r in enumerate(recipes)
            ]
            st.dataframe(
                overview_rows,
                use_container_width=True,
                hide_index=True,
                height=min(520, 48 + 38 * len(recipes)),
            )

            st.markdown("**维度展开（逐条平铺，无需点开）**")
            for i, r in enumerate(recipes):
                wc = r.get("word_count", len(recipe_pairs(r.get("parts"))))
                cm = r.get("combo_mode", "")
                with st.container(border=True):
                    st.markdown(f"##### 第 {i + 1} 条 · {wc} 词 · {cm}")
                    parts = recipe_pairs(r.get("parts"))
                    if parts:
                        n = len(parts)
                        cols = st.columns(n)
                        for j, (k, v) in enumerate(parts):
                            with cols[j]:
                                st.caption(f"{k} · 槽{j + 1}")
                                st.markdown(f"**{v}**")
                    st.markdown(f"`{r['summary']}`")

            err = st.session_state.get("eval_error")
            if err:
                st.error(f"自动评价失败：{err}")
                st.session_state.pop("eval_error", None)

    with col_side:
        st.subheader("AI 评价与存档")
        recipes = st.session_state.last_recipes

        pick = 0
        if recipes:
            pick = st.selectbox(
                "评价 / 存档对象",
                options=list(range(len(recipes))),
                format_func=lambda i: f"第 {i + 1} 条 · {recipes[i]['summary'][:40]}…",
                key="pick_recipe_idx",
            )
            cur = recipes[pick]
            ev = st.session_state.evaluations.get(pick)

            if st.button("对所选配方发送 AI 评价", use_container_width=True):
                try:
                    with st.spinner("正在请求 AI…"):
                        st.session_state.evaluations[pick] = evaluate(cur["summary"], prov)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

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
                    if st.button("保存到 Markdown", use_container_width=True, key="save_md"):
                        path = save_to_markdown(
                            cur["summary"],
                            cur["parts"],
                            ev_dict,
                        )
                        st.toast(f"已保存：{path.relative_to(ROOT)}")
                with s2:
                    if st.button("写入 SQLite", use_container_width=True, key="save_sql"):
                        rid = save_to_sqlite(
                            cur["summary"],
                            cur["parts"],
                            ev_dict,
                        )
                        st.toast(f"已写入数据库，id={rid}")
            else:
                st.caption("选择一条配方并点击「发送 AI 评价」，或批量生成时勾选侧栏「生成后自动评价第 1 条」。")
        else:
            st.write("生成配方后，在此选择条目进行评价与存档。")

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
