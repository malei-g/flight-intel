"""
flight-intel — Streamlit 看板 MVP
运行: PYTHONPATH=. uv run streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import FlightOption, ScoredFlight
from app.services.recommender import recommend

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flight Intel",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 主题 token（slate-cobalt，Inter）────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* slate 背景 */
    .stApp { background-color: #0f172a; color: #e2e8f0; }
    section[data-testid="stSidebar"] { background-color: #1e293b; }

    /* 卡片基础 */
    .fi-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 12px;
    }
    .fi-card-top {
        border-left: 4px solid #3b82f6;
    }
    .fi-card-mid { border-left: 4px solid #06b6d4; }
    .fi-card-low { border-left: 4px solid #64748b; }

    /* Badge */
    .badge-buy   { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }
    .badge-wait  { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }
    .badge-skip  { background:#fee2e2; color:#991b1b; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }

    /* Score ring label */
    .score-big { font-size:40px; font-weight:700; color:#f1f5f9; line-height:1; }
    .score-sub { font-size:12px; color:#94a3b8; margin-top:2px; }

    /* Mono numbers */
    .mono { font-family: 'JetBrains Mono', monospace; }

    /* 隐藏 Streamlit 默认页脚 */
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }

    /* 表格行色 */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 数据加载 ──────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_demo_flights(path: str) -> list[FlightOption]:
    raw = json.loads(Path(path).read_text())
    return [FlightOption(**f) for f in raw]


# ── 辅助函数 ──────────────────────────────────────────────────────────────────
def fmt_duration(mins: int) -> str:
    h, m = divmod(mins, 60)
    return f"{h}h {m:02d}m"


def badge_html(verdict: str) -> str:
    cls = {"BUY": "badge-buy", "WAIT": "badge-wait", "SKIP": "badge-skip"}.get(verdict, "badge-skip")
    return f'<span class="{cls}">{verdict}</span>'


def score_color(score: float) -> str:
    if score >= 70:
        return "#22d3ee"
    if score >= 55:
        return "#f59e0b"
    return "#f87171"


def card_class(rank: int) -> str:
    return {1: "fi-card fi-card-top", 2: "fi-card fi-card-mid"}.get(rank, "fi-card fi-card-low")


def breakdown_bars(bd: dict[str, float]) -> go.Figure:
    labels = ["价格", "时长", "中转次数", "中转风险", "时刻"]
    keys   = ["price_score", "duration_score", "stops_score", "transfer_risk_score", "time_comfort_score"]
    values = [bd.get(k, 0) for k in keys]
    colors = ["#22d3ee" if v >= 70 else "#f59e0b" if v >= 50 else "#f87171" for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors,
        text=[f"{v:.0f}" for v in values],
        textposition="outside",
        textfont=dict(color="#94a3b8", size=11),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=30, t=0, b=0),
        height=130,
        xaxis=dict(range=[0, 115], showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(tickfont=dict(color="#94a3b8", size=11), showgrid=False),
        showlegend=False,
    )
    return fig


# ── 页头 ──────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="padding:24px 0 8px 0;">
        <span style="font-size:28px;font-weight:700;color:#f1f5f9;">✈ Flight Intel</span>
        <span style="font-size:14px;color:#64748b;margin-left:12px;">智能机票评分看板</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 搜索表单 ──────────────────────────────────────────────────────────────────
with st.container():
    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1, 1])
    with c1:
        origin = st.text_input("出发地", value="PVG（上海浦东）", label_visibility="visible")
    with c2:
        destination = st.text_input("目的地", value="DTW（底特律）", label_visibility="visible")
    with c3:
        default_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        depart_date = st.text_input("出发日期", value=default_date)
    with c4:
        top_n = st.selectbox("显示 Top N", [3, 5, 10], index=0)
    with c5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        search_btn = st.button("搜索 / 刷新", use_container_width=True, type="primary")

st.divider()

# ── 权重滑块（侧边栏）────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙ 打分权重调整")
    st.caption("合计须为 1.0，调整后自动重算")

    w_price    = st.slider("💰 价格",      0.0, 1.0, 0.40, 0.05)
    w_duration = st.slider("⏱ 总时长",    0.0, 1.0, 0.25, 0.05)
    w_stops    = st.slider("🔀 中转次数",  0.0, 1.0, 0.20, 0.05)
    w_risk     = st.slider("⚠ 中转风险",  0.0, 1.0, 0.10, 0.05)
    w_comfort  = st.slider("🌙 时刻舒适",  0.0, 1.0, 0.05, 0.05)

    total_w = round(w_price + w_duration + w_stops + w_risk + w_comfort, 2)
    if abs(total_w - 1.0) > 0.01:
        st.warning(f"当前合计 = {total_w:.2f}，建议调整至 1.0")
    else:
        st.success(f"权重合计 ✓ {total_w:.2f}")

    st.divider()
    st.markdown("**数据来源**")
    data_source = st.radio(
        "",
        ["Demo 数据", "Google Flights（实时）"],
        index=0,
        help="Google Flights 实时查询需要网络，首次约 5 秒",
    )
    if data_source == "Google Flights（实时）":
        st.caption("点击「搜索 / 刷新」触发实时查询")


# ── 加载 & 打分 ───────────────────────────────────────────────────────────────
demo_path = str(Path(__file__).parent.parent / "data" / "raw" / "demo_flights.json")

@st.cache_data(show_spinner=False, ttl=300)
def load_google_flights(origin: str, dest: str, depart: str) -> list[FlightOption]:
    from app.schemas import SearchConfig
    from app.services.flight_fetcher import fetch_flights
    config = SearchConfig(origin=origin, destination=dest, depart_date=depart)
    return fetch_flights(config, provider="google")

# 解析表单里的 IATA 代码（兼容 "PVG（上海浦东）" 写法）
_iata_origin = origin.split("（")[0].strip().upper()[:3]
_iata_dest   = destination.split("（")[0].strip().upper()[:3]

use_google = data_source == "Google Flights（实时）"
spinner_msg = "正在查询 Google Flights…（首次约 5s）" if use_google else "加载 Demo 数据并打分…"

with st.spinner(spinner_msg):
    from app.services.scorer import ScoringWeights
    weights = ScoringWeights(
        price=w_price, duration=w_duration, stops=w_stops,
        transfer_risk=w_risk, time_comfort=w_comfort,
    )
    if use_google:
        all_flights = load_google_flights(_iata_origin, _iata_dest, depart_date)
        if not all_flights:
            st.warning("Google Flights 返回 0 条数据，已 fallback 到 Demo 数据")
            all_flights = load_demo_flights(demo_path)
    else:
        all_flights = load_demo_flights(demo_path)

    all_scored: list[ScoredFlight] = recommend(all_flights, top_n=len(all_flights), weights=weights)
    top_scored = all_scored[:top_n]


# ── KPI 汇总行 ────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
prices = [f.flight.price_usd for f in all_scored]
durs   = [f.flight.total_duration_min for f in all_scored]

with k1:
    st.metric("候选航班数", len(all_scored))
with k2:
    best = all_scored[0]
    st.metric("最高评分", f"{best.score:.1f}", delta=best.buy_or_wait)
with k3:
    st.metric("最低票价", f"${min(prices):.0f}", delta=f"均价 ${sum(prices)/len(prices):.0f}")
with k4:
    mn, mx = min(durs), max(durs)
    st.metric("最短时长", fmt_duration(mn), delta=f"最长 {fmt_duration(mx)}")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


# ── Top N 推荐卡片 ────────────────────────────────────────────────────────────
st.markdown(f"### 🏆 Top {top_n} 推荐航班")

for sf in top_scored:
    f = sf.flight
    bd = sf.breakdown.model_dump()
    h, m = divmod(f.total_duration_min, 60)
    stops_txt = "直飞" if f.stops == 0 else f"{f.stops} 次中转"
    dep_time = f.segments[0].depart_time.strftime("%H:%M") if f.segments else "—"

    with st.container():
        left, mid, right = st.columns([1, 3, 2])

        with left:
            st.markdown(
                f"""
                <div style="text-align:center;padding:12px 0;">
                  <div class="score-big" style="color:{score_color(sf.score)};">{sf.score:.0f}</div>
                  <div class="score-sub">评分 / 100</div>
                  <div style="margin-top:10px;">{badge_html(sf.buy_or_wait)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with mid:
            st.markdown(
                f"""
                <div class="{card_class(sf.rank)}" style="height:100%;">
                  <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                    <span style="font-size:18px;font-weight:700;color:#f1f5f9;">#{sf.rank}</span>
                    <span style="font-size:15px;font-weight:600;color:#e2e8f0;">{f.segments[0].airline if f.segments else '—'}</span>
                    <span style="font-size:13px;color:#64748b;">{f.id}</span>
                  </div>
                  <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px;">
                    <span class="mono" style="color:#22d3ee;font-size:22px;font-weight:600;">${f.price_usd:,.0f}</span>
                    <span style="color:#94a3b8;font-size:14px;margin-top:5px;">⏱ {h}h {m:02d}m &nbsp;|&nbsp; {stops_txt} &nbsp;|&nbsp; 起飞 {dep_time}</span>
                  </div>
                  <div style="font-size:13px;color:#94a3b8;line-height:1.6;">{sf.recommend_reason}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with right:
            st.markdown(
                "<div style='font-size:11px;color:#64748b;margin-bottom:4px;'>分项评分</div>",
                unsafe_allow_html=True,
            )
            st.plotly_chart(breakdown_bars(bd), use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


# ── 全量结果表格 ──────────────────────────────────────────────────────────────
st.markdown("### 📋 全部候选航班")

rows = []
for sf in all_scored:
    f = sf.flight
    h, m = divmod(f.total_duration_min, 60)
    bd = sf.breakdown
    rows.append({
        "排名": sf.rank,
        "航班 ID": f.id,
        "航司": f.segments[0].airline if f.segments else "—",
        "票价 ($)": f.price_usd,
        "总时长": f"{h}h{m:02d}m",
        "中转次数": f.stops,
        "起飞时间": f.segments[0].depart_time.strftime("%H:%M") if f.segments else "—",
        "评分": sf.score,
        "建议": sf.buy_or_wait,
        "价格分": bd.price_score,
        "时长分": bd.duration_score,
        "中转分": bd.stops_score,
    })

df = pd.DataFrame(rows)

# 列宽配置
col_cfg = {
    "排名": st.column_config.NumberColumn(width="small"),
    "票价 ($)": st.column_config.NumberColumn(format="$%.0f"),
    "评分": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
    "建议": st.column_config.TextColumn(width="small"),
}
st.dataframe(df, use_container_width=True, hide_index=True, column_config=col_cfg)


# ── 图表区 ────────────────────────────────────────────────────────────────────
st.markdown("### 📊 数据分布")
ch1, ch2 = st.columns(2)

# 价格分布直方图
with ch1:
    st.markdown("##### 票价分布")
    fig_hist = px.histogram(
        df, x="票价 ($)", nbins=12,
        color_discrete_sequence=["#3b82f6"],
        labels={"票价 ($)": "票价 (USD)", "count": "航班数"},
    )
    fig_hist.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1e293b",
        font_color="#94a3b8",
        xaxis=dict(gridcolor="#334155"),
        yaxis=dict(gridcolor="#334155"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=260,
        bargap=0.1,
    )
    fig_hist.update_traces(marker_line_color="#1d4ed8", marker_line_width=1)
    st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

# 时长 vs 价格散点图
with ch2:
    st.markdown("##### 时长 vs 票价（气泡大小 = 评分）")

    # 把中转次数转成字符串避免 Plotly 把它当连续值
    scatter_df = df.copy()
    scatter_df["中转"] = scatter_df["中转次数"].map({0: "直飞", 1: "1次中转", 2: "2次中转"}).fillna("3次+")
    scatter_df["时长(min)"] = [f.flight.total_duration_min for f in all_scored]

    fig_scatter = px.scatter(
        scatter_df,
        x="时长(min)", y="票价 ($)",
        size="评分", color="中转",
        hover_data=["航班 ID", "航司", "评分", "建议"],
        color_discrete_map={"直飞": "#22d3ee", "1次中转": "#3b82f6", "2次中转": "#a78bfa", "3次+": "#f87171"},
        size_max=24,
    )
    fig_scatter.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1e293b",
        font_color="#94a3b8",
        xaxis=dict(gridcolor="#334155", title="总时长（分钟）"),
        yaxis=dict(gridcolor="#334155", title="票价（USD）"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8")),
        margin=dict(l=0, r=0, t=10, b=0),
        height=260,
    )
    st.plotly_chart(fig_scatter, use_container_width=True, config={"displayModeBar": False})


# ── 页脚 ──────────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div style="margin-top:32px;padding-top:16px;border-top:1px solid #334155;
                color:#475569;font-size:12px;text-align:center;">
        Flight Intel &nbsp;·&nbsp; 数据来源: {"Google Flights" if use_google else "Demo"} &nbsp;·&nbsp; {_iata_origin}→{_iata_dest}
        &nbsp;·&nbsp; 航班数: {len(all_scored)} &nbsp;·&nbsp;
        更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
    """,
    unsafe_allow_html=True,
)
