"""
flight-intel — Streamlit 看板 v2（真实数据 + SQLite 历史）
运行: PYTHONPATH=. uv run streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import list_sessions, load_session_flights, price_history, historical_avg_price
from app.services.adjacent_baseline import fetch_adjacent_baseline
from app.schemas import FlightOption, ScoredFlight
from app.services.recommender import recommend
from app.services.scorer import ScoringWeights

# ── 页面配置 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Flight Intel",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0f172a; color: #e2e8f0; }
section[data-testid="stSidebar"] { background-color: #1e293b; }
.fi-card { background:#1e293b; border:1px solid #334155; border-radius:12px; padding:20px 24px; margin-bottom:12px; }
.fi-card-top { border-left:4px solid #3b82f6; }
.fi-card-mid  { border-left:4px solid #06b6d4; }
.fi-card-low  { border-left:4px solid #64748b; }
.badge-buy  { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }
.badge-wait { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }
.badge-skip { background:#fee2e2; color:#991b1b; padding:3px 10px; border-radius:99px; font-size:12px; font-weight:600; }
.score-big { font-size:40px; font-weight:700; color:#f1f5f9; line-height:1; }
.score-sub { font-size:12px; color:#94a3b8; margin-top:2px; }
.mono { font-family:'JetBrains Mono',monospace; }
footer { visibility:hidden; } #MainMenu { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


# ── 辅助函数 ──────────────────────────────────────────────────────────────────
def fmt_dur(mins: int) -> str:
    h, m = divmod(mins, 60)
    return f"{h}h {m:02d}m"

def badge_html(v: str) -> str:
    cls = {"BUY":"badge-buy","WAIT":"badge-wait","SKIP":"badge-skip"}.get(v,"badge-skip")
    return f'<span class="{cls}">{v}</span>'

def score_color(s: float) -> str:
    return "#22d3ee" if s >= 70 else "#f59e0b" if s >= 55 else "#f87171"

def card_cls(rank: int) -> str:
    return {1:"fi-card fi-card-top",2:"fi-card fi-card-mid"}.get(rank,"fi-card fi-card-low")

def breakdown_bars(bd: dict) -> go.Figure:
    labels = ["价格","时长","中转数","中转风险","时刻"]
    keys   = ["price_score","duration_score","stops_score","transfer_risk_score","time_comfort_score"]
    vals   = [bd.get(k,0) for k in keys]
    colors = ["#22d3ee" if v>=70 else "#f59e0b" if v>=50 else "#f87171" for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h",
        marker_color=colors,
        text=[f"{v:.0f}" for v in vals], textposition="outside",
        textfont=dict(color="#94a3b8", size=11),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0,r=30,t=0,b=0), height=130,
        xaxis=dict(range=[0,115],showticklabels=False,showgrid=False,zeroline=False),
        yaxis=dict(tickfont=dict(color="#94a3b8",size=11),showgrid=False),
        showlegend=False,
    )
    return fig

_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1e293b", font_color="#94a3b8",
    margin=dict(l=0,r=0,t=10,b=0), height=260,
)


# ── 页头 ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:24px 0 4px 0;">
  <span style="font-size:28px;font-weight:700;color:#f1f5f9;">✈ Flight Intel</span>
  <span style="font-size:14px;color:#64748b;margin-left:12px;">智能机票评分看板 · Google Flights 实时数据</span>
</div>
<div style="font-size:12px;color:#475569;padding-bottom:12px;">
  航班号（如 <code style="background:#1e293b;padding:1px 5px;border-radius:4px;color:#38bdf8;">AC-001</code>）
  为系统按航司 IATA 代码自动生成的<strong>虚拟标识</strong>，非真实航班号，仅供排序与追踪使用。
</div>
""", unsafe_allow_html=True)


# ── 搜索表单 ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1, 1])
with c1:
    origin_raw = st.text_input("出发地", value="PVG（上海浦东）")
with c2:
    dest_raw = st.text_input("目的地", value="DTW（底特律）")
with c3:
    default_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    depart_date = st.text_input("出发日期", value=default_date)
with c4:
    top_n = st.selectbox("Top N", [3, 5, 10], index=1)
with c5:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    fetch_btn = st.button("查询 Google Flights", use_container_width=True, type="primary")

_iata_o = origin_raw.split("（")[0].strip().upper()[:3]
_iata_d = dest_raw.split("（")[0].strip().upper()[:3]

st.divider()


# ── 侧边栏：权重 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙ 打分权重")
    st.caption("合计须为 1.0")
    w_price    = st.slider("💰 价格",     0.0, 1.0, 0.40, 0.05)
    w_duration = st.slider("⏱ 总时长",   0.0, 1.0, 0.25, 0.05)
    w_stops    = st.slider("🔀 中转次数", 0.0, 1.0, 0.20, 0.05)
    w_risk     = st.slider("⚠ 中转风险", 0.0, 1.0, 0.10, 0.05)
    w_comfort  = st.slider("🌙 时刻舒适", 0.0, 1.0, 0.05, 0.05)
    total_w = round(w_price + w_duration + w_stops + w_risk + w_comfort, 2)
    (st.success if abs(total_w - 1.0) <= 0.01 else st.warning)(
        f"权重合计 {'✓' if abs(total_w-1.0)<=0.01 else '⚠'} {total_w:.2f}"
    )
    st.divider()
    st.markdown("**视图模式**")
    view_mode = st.radio("", ["实时查询", "历史记录"], index=0, label_visibility="collapsed")


# ── 数据加载 ──────────────────────────────────────────────────────────────────
weights = ScoringWeights(
    price=w_price, duration=w_duration, stops=w_stops,
    transfer_risk=w_risk, time_comfort=w_comfort,
)

@st.cache_data(show_spinner=False, ttl=300)
def _fetch_and_score(origin: str, dest: str, depart: str) -> list[ScoredFlight]:
    from app.schemas import SearchConfig
    from app.services.flight_fetcher import fetch_flights
    from app.db import save_session
    config = SearchConfig(origin=origin, destination=dest, depart_date=depart)
    flights = fetch_flights(config)
    hist_avg = historical_avg_price(origin, dest, depart)
    if hist_avg is None:
        hist_avg = fetch_adjacent_baseline(origin, dest, depart)
    scored = recommend(flights, top_n=len(flights), hist_avg_price=hist_avg)
    try:
        save_session(config, scored)
    except Exception:
        pass
    return scored

# ── 模式：历史记录 ────────────────────────────────────────────────────────────
if view_mode == "历史记录":
    st.markdown("### 📂 历史抓取记录")
    sessions = list_sessions(_iata_o, _iata_d, limit=30)
    if not sessions:
        st.info("暂无历史记录。切换到「实时查询」先抓取一次。")
        st.stop()

    # 会话选择器
    session_labels = {
        s["id"]: f"#{s['id']}  {s['fetched_at']}  ({s['flight_count']} 条)  {s.get('price_level','')}"
        for s in sessions
    }
    selected_id = st.selectbox(
        "选择历史会话",
        options=list(session_labels.keys()),
        format_func=lambda x: session_labels[x],
    )
    rows_raw = load_session_flights(selected_id)
    if not rows_raw:
        st.warning("该会话无数据")
        st.stop()

    # 重建 ScoredFlight，以便复用权重重算
    import json as _json
    flights_rebuild: list[FlightOption] = []
    for r in rows_raw:
        try:
            flights_rebuild.append(FlightOption.model_validate_json(r["raw_flight"]))
        except Exception:
            pass
    if flights_rebuild:
        hist_avg = historical_avg_price(_iata_o, _iata_d, depart_date)
        all_scored = recommend(flights_rebuild, top_n=len(flights_rebuild), weights=weights, hist_avg_price=hist_avg)
    else:
        st.error("无法解析历史数据")
        st.stop()

    # 价格历史趋势图
    trend = price_history(_iata_o, _iata_d, depart_date, top_n=5)
    if len(trend) > 1:
        st.markdown("### 📈 价格历史趋势（Top-5 最低价 / 均价）")
        trend_df = pd.DataFrame(trend)
        trend_df["fetched_at"] = pd.to_datetime(trend_df["fetched_at"])
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=trend_df["fetched_at"], y=trend_df["min_price"],
            name="最低价", mode="lines+markers",
            line=dict(color="#22d3ee", width=2),
            marker=dict(size=6),
        ))
        fig_trend.add_trace(go.Scatter(
            x=trend_df["fetched_at"], y=trend_df["avg_price"],
            name="均价", mode="lines+markers",
            line=dict(color="#f59e0b", width=2, dash="dot"),
            marker=dict(size=6),
        ))
        fig_trend.update_layout(
            **_CHART_LAYOUT,
            height=220,
            xaxis=dict(gridcolor="#334155", title="抓取时间"),
            yaxis=dict(gridcolor="#334155", title="票价 (USD)"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8")),
        )
        st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

    top_scored = all_scored[:top_n]

# ── 模式：实时查询 ────────────────────────────────────────────────────────────
else:
    if not fetch_btn and "last_scored" not in st.session_state:
        st.info("点击「查询 Google Flights」获取实时数据。")
        st.stop()

    if fetch_btn:
        with st.spinner(f"正在查询 Google Flights {_iata_o}→{_iata_d}…（约 5s）"):
            try:
                st.session_state["last_scored"] = _fetch_and_score(_iata_o, _iata_d, depart_date)
                st.session_state["last_query"] = (_iata_o, _iata_d, depart_date)
            except Exception as e:
                st.error(f"查询失败: {e}")
                st.stop()

    all_scored = st.session_state["last_scored"]
    # 权重改变时在本地重算，不重新抓取
    raw_flights = [sf.flight for sf in all_scored]
    all_scored = recommend(raw_flights, top_n=len(raw_flights), weights=weights)
    top_scored = all_scored[:top_n]


# ── KPI 行 ────────────────────────────────────────────────────────────────────
prices = [sf.flight.price_usd for sf in all_scored]
durs   = [sf.flight.total_duration_min for sf in all_scored]

k1, k2, k3, k4 = st.columns(4)
with k1: st.metric("候选航班数", len(all_scored))
with k2:
    best = all_scored[0]
    st.metric("最高评分", f"{best.score:.1f}", delta=best.buy_or_wait)
with k3:
    st.metric("最低票价", f"${min(prices):.0f}", delta=f"均价 ${sum(prices)/len(prices):.0f}")
with k4:
    st.metric("最短时长", fmt_dur(min(durs)), delta=f"最长 {fmt_dur(max(durs))}")

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
            st.markdown(f"""
            <div style="text-align:center;padding:12px 0;">
              <div class="score-big" style="color:{score_color(sf.score)};">{sf.score:.0f}</div>
              <div class="score-sub">评分 / 100</div>
              <div style="margin-top:10px;">{badge_html(sf.buy_or_wait)}</div>
            </div>""", unsafe_allow_html=True)
        with mid:
            airline = f.segments[0].airline if f.segments else "—"
            flight_no = f.segments[0].flight_no if f.segments else f.id
            st.markdown(f"""
            <div class="{card_cls(sf.rank)}" style="height:100%;">
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                <span style="font-size:18px;font-weight:700;color:#f1f5f9;">#{sf.rank}</span>
                <span style="font-size:15px;font-weight:600;color:#e2e8f0;">{airline}</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:13px;
                             color:#38bdf8;background:#0f2942;padding:2px 8px;
                             border-radius:6px;letter-spacing:0.05em;"
                      title="虚拟航班号（系统生成，非真实航班号）">{flight_no} <sup style="font-size:9px;color:#64748b;">虚拟</sup></span>
              </div>
              <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px;">
                <span class="mono" style="color:#22d3ee;font-size:22px;font-weight:600;">${f.price_usd:,.0f}</span>
                <span style="color:#94a3b8;font-size:14px;margin-top:5px;">
                  ⏱ {h}h {m:02d}m &nbsp;|&nbsp; {stops_txt} &nbsp;|&nbsp; 起飞 {dep_time}
                </span>
              </div>
              <div style="font-size:13px;color:#94a3b8;line-height:1.6;">{sf.recommend_reason}</div>
            </div>""", unsafe_allow_html=True)
        with right:
            st.markdown("<div style='font-size:11px;color:#64748b;margin-bottom:4px;'>分项评分</div>",
                        unsafe_allow_html=True)
            st.plotly_chart(breakdown_bars(bd), use_container_width=True,
                            config={"displayModeBar": False})
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


# ── 全量表格 ──────────────────────────────────────────────────────────────────
st.markdown("### 📋 全部候选航班")
rows = []
for sf in all_scored:
    f = sf.flight
    h, m = divmod(f.total_duration_min, 60)
    bd = sf.breakdown
    rows.append({
        "排名": sf.rank,
        "航班号": f.segments[0].flight_no if f.segments else f.id,
        "航司": f.segments[0].airline if f.segments else "—",
        "票价 ($)": f.price_usd,
        "总时长": f"{h}h{m:02d}m",
        "中转": f.stops,
        "起飞": f.segments[0].depart_time.strftime("%H:%M") if f.segments else "—",
        "评分": sf.score,
        "建议": sf.buy_or_wait,
        "价格分": bd.price_score,
        "时长分": bd.duration_score,
        "中转分": bd.stops_score,
    })
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True, column_config={
    "排名": st.column_config.NumberColumn(width="small"),
    "航班号": st.column_config.TextColumn(
        help="虚拟航班号（航司 IATA 代码 + 序号，系统自动生成，非真实航班号）",
        width="small",
    ),
    "票价 ($)": st.column_config.NumberColumn(format="$%.0f"),
    "评分": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
    "建议": st.column_config.TextColumn(width="small"),
})


# ── 分布图 ────────────────────────────────────────────────────────────────────
st.markdown("### 📊 数据分布")
ch1, ch2 = st.columns(2)

with ch1:
    st.markdown("##### 票价分布")
    fig_hist = px.histogram(df, x="票价 ($)", nbins=14,
                            color_discrete_sequence=["#3b82f6"])
    fig_hist.update_layout(**_CHART_LAYOUT,
                           xaxis=dict(gridcolor="#334155"),
                           yaxis=dict(gridcolor="#334155"), bargap=0.1)
    fig_hist.update_traces(marker_line_color="#1d4ed8", marker_line_width=1)
    st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

with ch2:
    st.markdown("##### 时长 vs 票价")
    sdf = df.copy()
    sdf["中转类型"] = sdf["中转"].map({0:"直飞",1:"1次中转",2:"2次中转"}).fillna("3次+")
    sdf["时长(min)"] = [sf.flight.total_duration_min for sf in all_scored]
    fig_sc = px.scatter(
        sdf, x="时长(min)", y="票价 ($)", size="评分", color="中转类型",
        hover_data=["航司","评分","建议"],
        color_discrete_map={"直飞":"#22d3ee","1次中转":"#3b82f6","2次中转":"#a78bfa","3次+":"#f87171"},
        size_max=24,
    )
    fig_sc.update_layout(**_CHART_LAYOUT,
                         xaxis=dict(gridcolor="#334155", title="总时长（分钟）"),
                         yaxis=dict(gridcolor="#334155", title="票价（USD）"),
                         legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8")))
    st.plotly_chart(fig_sc, use_container_width=True, config={"displayModeBar": False})


# ── 页脚 ──────────────────────────────────────────────────────────────────────
q = st.session_state.get("last_query", (_iata_o, _iata_d, depart_date))
st.markdown(f"""
<div style="margin-top:32px;padding-top:16px;border-top:1px solid #334155;
            color:#475569;font-size:12px;text-align:center;">
  Flight Intel &nbsp;·&nbsp; Google Flights 实时数据 &nbsp;·&nbsp;
  {q[0]}→{q[1]} &nbsp;·&nbsp; 航班数: {len(all_scored)} &nbsp;·&nbsp;
  {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
""", unsafe_allow_html=True)
