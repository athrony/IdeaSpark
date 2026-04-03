"""
IdeaSpark — Streamlit entry: word banks, random recipes, AI evaluation, persistence.
"""

from __future__ import annotations

import logging
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
            "GEMINI_RELAY_PROTOCOL",
            "GEMINI_RELAY_AUTH",
            "WEBHOOK_URL",
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
from ideaspark.batch_evaluator import evaluate_batch, merge_kept_results
from ideaspark.webhook_notify import build_batch_payload, post_json_webhook
from ideaspark.cartesian import sample_cartesian_recipes
from ideaspark.combinator import draw_recipe, recipe_nouns_join, recipe_pairs
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


def _webhook_url_resolved() -> str:
    """优先使用当前页 Webhook 输入框，其次 Secrets / 环境变量。"""
    u = (st.session_state.get("webhook_url_input") or "").strip()
    if u:
        return u
    return (os.environ.get("WEBHOOK_URL") or "").strip()


def _relay_kwargs_for_batch() -> dict[str, str | None]:
    """侧栏 session 与 Secrets/.env 合并，供批量评审显式传入（避免仅依赖 os.environ 时序）。"""
    rb = (st.session_state.get("relay_base_url_input") or "").strip()
    if not rb:
        rb = (os.environ.get("GEMINI_RELAY_BASE_URL") or "").strip()
    rk = (st.session_state.get("relay_api_key_input") or "").strip()
    if not rk:
        rk = (
            os.environ.get("GEMINI_RELAY_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        ).strip()
    rm = (st.session_state.get("relay_model_input") or "").strip()
    if not rm:
        rm = (os.environ.get("GEMINI_RELAY_MODEL") or "Gemini 3.1 Flash-Lite").strip()
    rp = (
        st.session_state.get("relay_protocol_input")
        or os.environ.get("GEMINI_RELAY_PROTOCOL")
        or "openai"
    ).strip()
    if rp not in ("openai", "gemini_rest"):
        rp = "openai"
    return {
        "relay_base_url": rb or None,
        "relay_api_key": rk or None,
        "relay_model": rm or None,
        "relay_protocol": rp,
    }


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
    if "pipeline_kept" not in st.session_state:
        st.session_state.pipeline_kept = []

    init_db()

    with st.sidebar:
        st.subheader("AI 设置")
        prov = st.radio(
            "API 提供商",
            options=["gemini", "relay", "openai"],
            index=_provider_radio_index(),
            format_func=lambda x: {
                "gemini": "Gemini 官方直连",
                "relay": "中转（OpenAI 兼容 或 Gemini 原生）",
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
                "说明见 [魔芋文档](http://101.200.167.88:8001/#text-gemini)。"
                "若中转提供 **OpenAI 兼容** 网关用第一项；只有 **Gemini 原生** 接口时用第二项。"
            )
            if "relay_protocol_input" not in st.session_state:
                rp0 = (os.environ.get("GEMINI_RELAY_PROTOCOL") or "openai").strip().lower()
                st.session_state.relay_protocol_input = (
                    rp0 if rp0 in ("openai", "gemini_rest") else "openai"
                )
            st.radio(
                "中转接口类型",
                options=["openai", "gemini_rest"],
                format_func=lambda x: {
                    "openai": "OpenAI 兼容（…/v1/chat/completions）",
                    "gemini_rest": "Gemini 原生（…/v1beta/…:generateContent）",
                }[x],
                key="relay_protocol_input",
                horizontal=True,
            )
            _rp = st.session_state.get("relay_protocol_input", "openai")
            if _rp == "gemini_rest":
                st.caption(
                    "请填 **站点根**（如 `https://www.moyu.info`），也可粘贴完整 generateContent 链接，程序会只保留域名。"
                    "模型名须与魔芋文档 **完全一致**（常见如 `gemini-2.0-flash`）。"
                    "若出现 **503 / 无可用渠道（distributor）**：表示该模型在你账号或默认分组下暂无路由，请换文档里其它可用模型，或联系魔芋。"
                    "若 **401** 可试在 secrets 设 `GEMINI_RELAY_AUTH`=`bearer`。"
                )
            else:
                st.caption(
                    "填 OpenAI 兼容网关根路径，程序会请求 `…/v1/chat/completions`。"
                )
            if "relay_base_url_input" not in st.session_state:
                st.session_state.relay_base_url_input = os.environ.get(
                    "GEMINI_RELAY_BASE_URL", ""
                )
            if "relay_api_key_input" not in st.session_state:
                st.session_state.relay_api_key_input = os.environ.get(
                    "GEMINI_RELAY_API_KEY", os.environ.get("GOOGLE_API_KEY", "")
                )
            if "relay_model_input" not in st.session_state:
                _env_m = (os.environ.get("GEMINI_RELAY_MODEL") or "").strip()
                if _env_m:
                    st.session_state.relay_model_input = _env_m
                else:
                    _rp0 = st.session_state.get("relay_protocol_input", "openai")
                    st.session_state.relay_model_input = (
                        "gemini-2.0-flash"
                        if _rp0 == "gemini_rest"
                        else "Gemini 3.1 Flash-Lite"
                    )
            st.text_input(
                "中转 Base URL",
                placeholder=(
                    "https://www.moyu.info"
                    if _rp == "gemini_rest"
                    else "http://101.200.167.88:8001/v1"
                ),
                help=(
                    "Gemini 原生：站点根，勿手写 :generateContent。"
                    if _rp == "gemini_rest"
                    else "OpenAI 兼容：以 /v1 结尾或只填到端口由程序补全。"
                ),
                key="relay_base_url_input",
            )
            st.text_input(
                "中转 API Key",
                type="password",
                key="relay_api_key_input",
            )
            st.text_input(
                "中转模型名",
                key="relay_model_input",
            )
            rb = (st.session_state.relay_base_url_input or "").strip()
            rk = (st.session_state.relay_api_key_input or "").strip()
            rm = (st.session_state.relay_model_input or "").strip() or "Gemini 3.1 Flash-Lite"
            if rb:
                os.environ["GEMINI_RELAY_BASE_URL"] = rb
            if rk:
                os.environ["GEMINI_RELAY_API_KEY"] = rk
            os.environ["GEMINI_RELAY_MODEL"] = rm
            os.environ["GEMINI_RELAY_PROTOCOL"] = str(
                st.session_state.get("relay_protocol_input", "openai")
            )

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
            st.selectbox(
                "组合方式",
                options=list(_combo_labels.keys()),
                index=0,
                key="idea_combo_label",
                help="每一「词槽」独立随机选一类再选一词；同类可重复出现（如 技术+技术）。同一类内尽量抽不同词，词不够时才重复。",
            )
        with row2:
            batch_n = st.number_input(
                "本批生成数量",
                min_value=1,
                max_value=50,
                value=5,
                step=1,
                key="idea_batch_n",
                help="一次点击可生成多条互不相同的随机配方，便于快速浏览与筛选。",
            )
        _ck = st.session_state.get("idea_combo_label") or list(_combo_labels.keys())[0]
        combo_mode = _combo_labels[_ck]

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
            if (
                "idea_anchor_pick" not in st.session_state
                or st.session_state.idea_anchor_pick not in anchor_opts
            ):
                st.session_state.idea_anchor_pick = (
                    "行业" if "行业" in anchor_opts else anchor_opts[0]
                )
            anchor_pick = st.selectbox(
                "锚点维度",
                options=anchor_opts,
                key="idea_anchor_pick",
                help="首槽使用的维度；与锚点词一起构成必选组合。",
            )
        with hb4:
            correlation = st.slider(
                "关联度",
                min_value=0.0,
                max_value=1.0,
                value=0.45,
                step=0.05,
                key="idea_correlation",
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
                    "名词组合": recipe_nouns_join(r),
                    "词数": r.get("word_count", len(recipe_pairs(r.get("parts")))),
                    "组合模式": r.get("combo_mode", ""),
                    "技术摘要": r["summary"],
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
                    st.markdown(f"**名词组合：** `{recipe_nouns_join(r)}`")
                    parts = recipe_pairs(r.get("parts"))
                    if parts:
                        n = len(parts)
                        cols = st.columns(n)
                        for j, (k, v) in enumerate(parts):
                            with cols[j]:
                                st.caption(f"{k}")
                                st.markdown(f"**{v}**")
                    st.caption("技术摘要（含维度标签）")
                    st.code(r["summary"], language=None)

            err = st.session_state.get("eval_error")
            if err:
                st.error(f"自动评价失败：{err}")
                st.session_state.pop("eval_error", None)

        st.divider()
        st.subheader("批量流水线（省 Token · 一次评审多条）")
        st.caption(
            "同一请求内用「编号|摘要」紧凑输入，模型只返回 JSON 列表，无意义配方标为 drop，不展开长评。"
        )
        pq1, pq2, pq3, pq4 = st.columns(4)
        with pq1:
            pl_count = st.number_input("每轮生成条数", 5, 100, 50, key="pl_count")
        with pq2:
            pl_rounds = st.number_input("循环轮数", 1, 20, 1, key="pl_rounds")
        with pq3:
            pl_min = st.slider("最低平均分", 0.0, 10.0, 6.0, 0.5, key="pl_min")
        with pq4:
            pl_chunk = st.number_input("每批评审条数（切块）", 8, 60, 36, key="pl_chunk")
        pl_ex_weak = st.checkbox("筛掉 weak（仅保留 ok/good）", value=False, key="pl_ex_weak")
        wh_url = st.text_input(
            "Webhook URL（可选，POST application/json）",
            value=os.environ.get("WEBHOOK_URL", ""),
            key="webhook_url_input",
            help="将筛选后的条目以 JSON 推送到你的服务；可由中间层转发到飞书/企微/钉钉等。",
        )
        if wh_url.strip():
            os.environ["WEBHOOK_URL"] = wh_url.strip()

        pr1, pr2 = st.columns(2)
        with pr1:
            run_pl = st.button(
                "一键：生成 → 批量评审 → 筛选",
                type="primary",
                use_container_width=True,
                key="run_pipeline",
            )
        with pr2:
            push_wh = st.button(
                "推送上次筛选结果到 Webhook",
                use_container_width=True,
                key="push_webhook",
            )

        if run_pl:
            dim_order = st.session_state.get("dim_order") or cat_keys
            ck = st.session_state.get("idea_combo_label") or list(_combo_labels.keys())[0]
            combo_m = _combo_labels[ck]
            corr = float(st.session_state.get("idea_correlation", 0.45))
            ap = st.session_state.get("idea_anchor_pick", "（不使用锚点）")
            acat = None if ap == "（不使用锚点）" else ap
            aw_raw = (st.session_state.get("anchor_word_input") or "").strip()
            n_rounds = max(1, int(st.session_state.get("pl_rounds", 1)))
            n_per = max(1, int(st.session_state.get("pl_count", 50)))
            with st.status(f"流水线（共 {n_rounds} 轮，每轮 {n_per} 条）…", expanded=True) as pl_status:
                all_kept: list = []
                total_gen = 0
                rkw: dict = {}
                if prov == "relay":
                    rkw = _relay_kwargs_for_batch()
                    if not rkw.get("relay_base_url"):
                        st.error(
                            "中转模式需要填写侧栏「中转 Base URL」，或在 Streamlit Secrets / 环境变量中设置 GEMINI_RELAY_BASE_URL。"
                        )
                        st.stop()
                try:
                    for ri in range(n_rounds):
                        pl_status.update(
                            label=f"第 {ri + 1}/{n_rounds} 轮：生成 {n_per} 条 → 批量评审 → 筛选…",
                            state="running",
                        )
                        recipes = [
                            draw_recipe(
                                st.session_state.categories,
                                combo_mode=combo_m,
                                correlation=corr,
                                anchor_category=acat,
                                anchor_word=aw_raw if aw_raw else None,
                                category_order=dim_order,
                            )
                            for _ in range(n_per)
                        ]
                        total_gen += len(recipes)
                        items, _raw = evaluate_batch(
                            recipes,
                            prov,
                            chunk_size=int(pl_chunk),
                            **rkw,
                        )
                        kept = merge_kept_results(
                            recipes,
                            items,
                            min_avg=float(pl_min),
                            exclude_weak=bool(pl_ex_weak),
                        )
                        for row in kept:
                            row["round"] = ri + 1
                            row["display_id"] = f"R{ri + 1}-{row['id']}"
                        all_kept.extend(kept)
                    pl_status.update(label="流水线全部完成", state="complete")
                    st.session_state.pipeline_kept = all_kept
                    st.session_state.pipeline_meta = {
                        "generated": total_gen,
                        "rounds": n_rounds,
                        "kept": len(all_kept),
                    }
                except ValueError as err:
                    pl_status.update(label="失败", state="error")
                    st.error(err.args[0] if err.args else "批量评审未通过，请检查模型与网络后重试。")
                    st.stop()
                except Exception:
                    pl_status.update(label="失败", state="error")
                    logging.exception("一键流水线：批量评审未捕获异常")
                    st.error(
                        "批量评审出现未预期错误。可尝试减小每批评审条数、稍后重试；完整堆栈见 Cloud「Manage app」日志。"
                    )
                    st.stop()
            st.success(
                f"完成：共 {n_rounds} 轮，累计生成 {total_gen} 条，筛选保留 {len(all_kept)} 条。"
            )
            wh_auto = _webhook_url_resolved()
            if wh_auto and all_kept:
                ok_wh, msg_wh = post_json_webhook(
                    wh_auto,
                    build_batch_payload(
                        all_kept,
                        title="IdeaSpark 批量评审",
                        rounds=n_rounds,
                        generated=total_gen,
                    ),
                )
                if ok_wh:
                    st.success(f"已自动推送到 Webhook：{msg_wh}")
                else:
                    st.warning(f"Webhook 自动推送失败：{msg_wh}（可稍后用下方按钮重试）")
            elif all_kept and not wh_auto:
                st.caption("未配置 Webhook URL，已跳过自动推送；填写后可手动推送。")

        if push_wh and st.session_state.pipeline_kept:
            meta = st.session_state.get("pipeline_meta") or {}
            payload = build_batch_payload(
                st.session_state.pipeline_kept,
                title="IdeaSpark 批量评审",
                rounds=int(meta.get("rounds", 1)),
                generated=int(meta.get("generated", 0)),
            )
            url = _webhook_url_resolved()
            if not url:
                st.error("请先在本页填写 Webhook URL（或 Secrets 中的 WEBHOOK_URL）。")
            else:
                ok, msg = post_json_webhook(url, payload)
                if ok:
                    st.success(f"已推送：{msg}")
                else:
                    st.error(f"推送失败：{msg}")

        pk = st.session_state.get("pipeline_kept") or []
        if pk:
            st.markdown("**上次流水线筛选结果**")
            st.dataframe(
                [
                    {
                        "轮次": x.get("round", 1),
                        "编号": x.get("display_id", x["id"]),
                        "名词组合": x.get("nouns", ""),
                        "优化题名": x.get("optimized_name", ""),
                        "tier": x["tier"],
                        "avg": x["avg"],
                        "mp": x["mp"],
                        "tf": x["tf"],
                        "ib": x["ib"],
                        "摘要": x["summary"],
                        "点评": x.get("comment", ""),
                    }
                    for x in pk
                ],
                use_container_width=True,
                hide_index=True,
            )

    with col_side:
        st.subheader("AI 评价与存档")
        recipes = st.session_state.last_recipes

        pick = 0
        if recipes:
            pick = st.selectbox(
                "评价 / 存档对象",
                options=list(range(len(recipes))),
                format_func=lambda i: f"第 {i + 1} 条 · {recipe_nouns_join(recipes[i])[:36]}…",
                key="pick_recipe_idx",
            )
            cur = recipes[pick]
            ev = st.session_state.evaluations.get(pick)

            st.caption(f"名词组合：`{recipe_nouns_join(cur)}`")

            if st.button("对所选配方发送 AI 评价", use_container_width=True):
                try:
                    with st.spinner("正在请求 AI…"):
                        st.session_state.evaluations[pick] = evaluate(cur["summary"], prov)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            if ev:
                if ev.short_title:
                    st.markdown("**优化题名**")
                    st.info(ev.short_title)
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
                    "short_title": ev.short_title,
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
