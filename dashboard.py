"""
dashboard.py — Danelfin / TailAdmin-style stock screener.

Light theme, purple accent, horizontal stock cards with inline SVG
sparklines, native Streamlit column_config for the main table,
and an AI Copilot that reads its key from .env automatically.

Run:
    python -m streamlit run dashboard.py
"""

from __future__ import annotations
import os
from pathlib import Path

# Load .env first so OPENAI_API_KEY is available from os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CFG, SECTORS, TICKER_SLEEVE, TICKER_NAMES  # noqa: E402
from src import data as data_mod
from src import momentum, signals
from src import sentiment as sent_mod
from src import backtest as bt_mod

try:
    from src.scoring import compute_ai_score
    from src.fundamentals import get_fundamentals
    _HAS_SCORING = True
except ImportError:
    _HAS_SCORING = False

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

# API key from .env — no sidebar input needed
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Design tokens (NextAdmin light — see .claude/skills/design-system) ────────
ACCENT   = "#6366F1"   # indigo — buttons, active nav, links
ACCENT_SOFT = "#EEF2FF"  # indigo tint — icon chips, active nav bg, tags
SUCCESS  = "#22C55E"   # green — gains only
DANGER   = "#EF4444"   # red — losses only
WARNING  = "#F59E0B"   # amber
MUTED    = "#8A99AF"   # slate — secondary labels
BORDER   = "#E8ECF4"
CARD_BG  = "#FFFFFF"
APP_BG   = "#F5F7FB"
TEXT_PRI = "#1C2434"
TEXT_SEC = "#64748B"

# Plotly light chart colours
P_ACCENT  = ACCENT
P_MUTED   = "#8A99AF"
P_SUCCESS = SUCCESS
P_DANGER  = DANGER
P_GRID    = "#F1F5F9"
P_LINE    = "#E8ECF4"



# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Picker AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── CSS injection ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', system-ui, sans-serif !important; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 3rem !important; max-width: 100% !important; }

/* Sidebar — white NextAdmin style; colors come from [theme.sidebar] in
   .streamlit/config.toml, so only structural touches live here. */
[data-testid="stSidebar"] {
    border-right: 1px solid #E8ECF4 !important;
    box-shadow: 0 1px 3px rgba(16,24,40,0.04);
}
[data-testid="stSidebarContent"] { padding: 1.4rem 1.1rem; }
[data-testid="stSidebar"] hr { border-color: #E8ECF4 !important; }

/* Tabs — pill style */
.stTabs [data-baseweb="tab-list"] {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 5px;
    gap: 3px;
    border: 1px solid #E8ECF4;
    box-shadow: 0 1px 3px rgba(16,24,40,0.05);
    margin-bottom: 1.5rem;
}
.stTabs [data-baseweb="tab"] {
    color: #64748B;
    border-radius: 9px;
    padding: 8px 22px;
    font-weight: 500;
    font-size: 13px;
    background: transparent;
}
.stTabs [data-baseweb="tab"]:hover { background: #F8FAFC; color: #334155; }
.stTabs [aria-selected="true"] { background: #6366F1 !important; color: #FFFFFF !important; }
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Metric cards */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E8ECF4;
    border-radius: 16px;
    padding: 1.25rem 1.5rem !important;
    box-shadow: 0 1px 3px rgba(16,24,40,0.05);
}
[data-testid="stMetricLabel"] * { color: #64748B !important; font-size: 12px !important; font-weight: 500 !important; text-transform: uppercase; letter-spacing: 0.5px; }
[data-testid="stMetricValue"] { color: #1C2434 !important; font-size: 28px !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"] svg { display: none; }
[data-testid="stMetricDelta"] * { font-size: 12px !important; font-weight: 500 !important; }

/* Primary button */
.stButton > button {
    background: #6366F1 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 9px 22px !important;
    box-shadow: 0 2px 6px rgba(99,102,241,0.28) !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: #4F46E5 !important;
    box-shadow: 0 4px 12px rgba(99,102,241,0.38) !important;
    transform: translateY(-1px) !important;
}

/* Dataframe container */
.stDataFrame > div {
    border-radius: 16px !important;
    overflow: hidden !important;
    border: 1px solid #E8ECF4 !important;
    box-shadow: 0 1px 3px rgba(16,24,40,0.05) !important;
}

/* Inputs */
div[data-baseweb="select"] > div { background: #FFFFFF !important; border-color: #E8ECF4 !important; border-radius: 9px !important; }
.stTextInput input, .stNumberInput input, .stDateInput input { background: #FFFFFF !important; border-color: #E8ECF4 !important; border-radius: 9px !important; color: #1C2434 !important; }
[data-baseweb="tag"] { background: #EEF2FF !important; color: #6366F1 !important; border-radius: 6px !important; }

/* Expanders */
.streamlit-expanderHeader { background: #FFFFFF !important; border: 1px solid #E8ECF4 !important; border-radius: 12px !important; color: #334155 !important; }
.streamlit-expanderContent { background: #FFFFFF !important; border: 1px solid #E8ECF4 !important; border-top: none !important; border-radius: 0 0 12px 12px !important; }

/* Alerts */
.stAlert { border-radius: 12px !important; }
[data-testid="stNotification"] { border-radius: 12px !important; }

/* Chat messages */
[data-testid="stChatMessage"] { background: #FFFFFF; border: 1px solid #E8ECF4; border-radius: 12px !important; margin-bottom: 8px; }

/* Toggle */
[data-testid="stToggle"] label { color: #374151 !important; }

/* Dividers */
hr { border-color: #E8ECF4 !important; margin: 1.5rem 0 !important; }

/* Number input spinner buttons */
[data-testid="stNumberInput"] button { background: #F8FAFC !important; border-color: #E8ECF4 !important; color: #374151 !important; }

/* Download button */
.stDownloadButton > button { background: #F8FAFC !important; color: #374151 !important; border: 1px solid #E8ECF4 !important; border-radius: 9px !important; box-shadow: none !important; }
.stDownloadButton > button:hover { background: #F1F5F9 !important; box-shadow: none !important; transform: none !important; }
</style>
""", unsafe_allow_html=True)


# ── SVG sparkline helper ──────────────────────────────────────────────────────
def _sparkline(prices: list, color: str, w: int = 96, h: int = 40,
               uid: str = "s") -> str:
    """NextAdmin-style sparkline: smooth polyline + soft gradient area fill.
    Handles empty/short/constant series without erroring."""
    pts_in = [p for p in (prices or []) if p == p]  # drop NaN
    if len(pts_in) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    mn, mx = min(pts_in), max(pts_in)
    rng = (mx - mn) or 1.0
    xy = [
        (round(i / (len(pts_in) - 1) * w, 1),
         round((1 - (p - mn) / rng) * (h - 8) + 4, 1))
        for i, p in enumerate(pts_in)
    ]
    line = " ".join(f"{x},{y}" for x, y in xy)
    area = f"0,{h} " + line + f" {w},{h}"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="g{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#g{uid})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def _stock_card(ticker: str, price: float, mom: float | None, prices_90d: list) -> str:
    """NextAdmin-style stock card: logo chip + name, sparkline top-right,
    Total Share / Total Return rows below."""
    name   = TICKER_NAMES.get(ticker, ticker)[:20]
    m      = mom or 0.0
    color  = SUCCESS if m >= 0 else DANGER
    arrow  = "▲" if m >= 0 else "▼"
    sign   = "+" if m >= 0 else ""
    spark  = _sparkline(prices_90d, color, uid=ticker)
    initls = ticker[:4]
    return f"""
<div style="min-width:230px;max-width:250px;background:{CARD_BG};border-radius:16px;
 padding:18px 20px;border:1px solid {BORDER};
 box-shadow:0 1px 3px rgba(16,24,40,0.06);flex-shrink:0;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <div style="width:40px;height:40px;background:{ACCENT_SOFT};border-radius:50%;
     display:flex;align-items:center;justify-content:center;
     font-size:10px;font-weight:800;color:{ACCENT};letter-spacing:-0.5px;">{initls}</div>
    <div style="flex:1;min-width:0;">
      <div style="font-size:15px;font-weight:700;color:{TEXT_PRI};line-height:1.2;">{ticker}</div>
      <div style="font-size:11px;color:{MUTED};line-height:1.3;white-space:nowrap;
       overflow:hidden;text-overflow:ellipsis;">{name}</div>
    </div>
    <div>{spark}</div>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
    <div style="font-size:12px;color:{MUTED};">Total Share</div>
    <div style="font-size:16px;font-weight:700;color:{TEXT_PRI};">${price:,.2f}</div>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div style="font-size:12px;color:{MUTED};">Total Return</div>
    <div style="font-size:13px;font-weight:700;color:{color};">{sign}{m*100:.2f}% {arrow}</div>
  </div>
</div>"""


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">'
        f'<div style="width:34px;height:34px;background:{ACCENT};border-radius:10px;'
        f'display:flex;align-items:center;justify-content:center;font-size:18px;">📈</div>'
        f'<div><div style="color:{TEXT_PRI};font-size:16px;font-weight:700;">Stock Picker AI</div>'
        f'<div style="color:{MUTED};font-size:11px;">AI-Powered Screener</div></div></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(f'<div style="color:{MUTED};font-size:11px;font-weight:600;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;">DATA SOURCE</div>', unsafe_allow_html=True)
    source_mode = st.radio("", ["Live (yfinance)", "Offline Demo (synthetic)"], key="sb_mode", label_visibility="collapsed")
    offline = source_mode == "Offline Demo (synthetic)"
    start = st.text_input("Start date", CFG.universe.start_date, key="sb_start")
    end   = st.text_input("End date",   CFG.universe.end_date,   key="sb_end")

    st.divider()
    st.markdown(f'<div style="color:{MUTED};font-size:11px;font-weight:600;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;">SCREENER FILTERS</div>', unsafe_allow_html=True)
    action_filter = st.multiselect("Actions", ["BUY", "HOLD", "AVOID"],
                                   default=["BUY", "HOLD"], key="sb_act")
    sector_filter = st.multiselect("Sectors", sorted(set(SECTORS.values())),
                                   default=[], key="sb_sect",
                                   help="Empty = all sectors")
    min_score = st.slider("Min AI Score", 1.0, 10.0, 4.0, 0.5, key="sb_min")

    st.divider()
    st.markdown(
        f'<div style="color:{TEXT_SEC};font-size:11px;line-height:1.6;">'
        f'{"✅ OpenAI key loaded from .env" if OPENAI_KEY else "⚠️ Set OPENAI_API_KEY in .env to enable AI chat"}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption(f"Universe: {len(CFG.universe.tickers)} stocks · free data")
    st.caption("yfinance · RSS · Alpha Vantage")


# ── Price loading ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_prices(offline: bool, start: str, end: str):
    src  = "synthetic" if offline else "yfinance"
    allp = data_mod.load_prices(start=start, end=end, source=src, use_cache=not offline)
    px, bench = data_mod.split_universe_benchmark(allp)
    return px, (bench if bench is not None else px.mean(axis=1))


try:
    with st.spinner(f"Loading prices for {len(CFG.universe.tickers)} stocks…"):
        px, bench = get_prices(offline, start, end)
    load_err = None
except Exception as e:
    px, bench, load_err = None, None, str(e)

if load_err:
    st.error(f"Price load failed: {load_err}  \nEnable **Offline Demo** in the sidebar to explore without network.")
    st.stop()


# ── Plotly light theme ────────────────────────────────────────────────────────
def _theme(fig, h: int = 360):
    fig.update_layout(
        template="plotly_white", height=h,
        paper_bgcolor="white", plot_bgcolor="#F8FAFC",
        font=dict(family="Inter, system-ui, sans-serif", color="#334155", size=12),
        margin=dict(l=55, r=20, t=40, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=P_GRID, zerolinecolor=P_LINE,
                     showline=True, linecolor=P_LINE,
                     tickfont=dict(size=11, color="#64748B"))
    fig.update_yaxes(gridcolor=P_GRID, zerolinecolor=P_LINE,
                     showline=True, linecolor=P_LINE,
                     tickfont=dict(size=11, color="#64748B"))
    return fig


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_screener, tab_signals, tab_backtest, tab_sentiment, tab_config = st.tabs([
    "📈 SCREENER", "📋 SIGNALS", "📊 BACKTEST", "🧠 SENTIMENT", "⚙️ CONFIG",
])


# ─────────────────────────────────────────────────────────────────────────────
# SCREENER
# ─────────────────────────────────────────────────────────────────────────────
with tab_screener:
    hdr_l, hdr_r = st.columns([5, 1])
    hdr_l.subheader("AI Stock Screener")
    hdr_l.caption(f"Ranked by composite AI Score (1–10) · {len(px.columns)} stocks · data as of {px.index[-1].strftime('%d %b %Y')}")
    run_score = hdr_r.button("🔄 Refresh", key="sc_run")

    if not _HAS_SCORING:
        st.warning("src/scoring.py and src/fundamentals.py are required in the src/ directory.")
    else:
        if run_score or "sc_df" not in st.session_state:
            with st.spinner(f"Computing AI scores for {len(px.columns)} stocks…"):
                panels  = momentum.build_panels(px)
                tickers = px.columns.tolist()
                _spark  = 63  # ~3 months

                rows = []
                for t in tickers:
                    rows.append({
                        "ticker":        t,
                        "sector":        SECTORS.get(t, "Other"),
                        "sleeve":        TICKER_SLEEVE.get(t, "core"),
                        "last_price":    float(px[t].iloc[-1]),
                        "mom_12m":       float(panels["tsm"][t].iloc[-1])      if t in panels["tsm"].columns     else None,
                        "ratio_52w":     float(panels["ratio52"][t].iloc[-1])  if t in panels["ratio52"].columns else None,
                        "rsi":           float(panels["rsi"][t].iloc[-1])      if t in panels["rsi"].columns     else None,
                        "above_long_ma": int(px[t].iloc[-1] > panels["ma_long"][t].iloc[-1]) if t in panels["ma_long"].columns else 0,
                        "volatility":    float(panels["vol"][t].iloc[-1])      if t in panels["vol"].columns     else None,
                        "price_trend":   px[t].tail(_spark).tolist(),
                    })

                df_sc = pd.DataFrame(rows).set_index("ticker")

                if "macd_hist" in panels:
                    df_sc["macd_hist"] = panels["macd_hist"].iloc[-1].reindex(df_sc.index)

                # Latest sentiment from history log
                try:
                    p = Path(CFG.paths.sentiment_log)
                    if p.exists():
                        hist_s = pd.read_csv(p, parse_dates=["date"])
                        latest_s = hist_s.loc[hist_s.date == hist_s.date.max()]
                        df_sc["sentiment_score"] = (
                            latest_s.groupby("ticker")["score"].mean()
                            .reindex(df_sc.index).fillna(0)
                        )
                except Exception:
                    pass

                # Fundamentals (7-day disk cache)
                try:
                    fund_df = get_fundamentals(tickers)
                    df_sc = df_sc.join(fund_df, how="left")
                except Exception as e:
                    st.caption(f"Fundamentals unavailable — {e}")

                df_sc = compute_ai_score(df_sc)
                df_sc["action_badge"] = df_sc["action"].astype(str).map({
                    "BUY": "🟢 BUY", "HOLD": "🟡 HOLD", "AVOID": "🔴 AVOID",
                }).fillna("—")
                if "under_radar" in df_sc.columns:
                    df_sc.loc[df_sc["under_radar"], "action_badge"] += " 💎"
                st.session_state.sc_df = df_sc

        df_sc = st.session_state.sc_df

        # ── Summary metrics ───────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🟢 BUY Signals",  int((df_sc["action"] == "BUY").sum()))
        m2.metric("🟡 HOLD Signals", int((df_sc["action"] == "HOLD").sum()))
        m3.metric("🔴 Avoid",        int((df_sc["action"] == "AVOID").sum()))
        m4.metric("Avg AI Score",    f"{df_sc['ai_score'].mean():.1f} / 10")

        # ── Top pick cards (horizontal scroll) ───────────────────────────────
        top_picks = df_sc.sort_values("ai_score", ascending=False).head(8)
        cards_html = "".join(
            _stock_card(
                ticker=t,
                price=row["last_price"],
                mom=row.get("mom_12m"),
                prices_90d=row["price_trend"],
            )
            for t, row in top_picks.iterrows()
        )
        st.markdown(
            f'<div style="display:flex;gap:14px;overflow-x:auto;padding:16px 2px 20px 2px;'
            f'scrollbar-width:thin;scrollbar-color:#CBD5E1 transparent;">'
            f'{cards_html}</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Strategy views (ProPicks-style preset screens) ────────────────────
        view = st.selectbox(
            "Strategy view",
            ["🌐 All stocks", "⭐ Top Value", "💎 Under the Radar",
             "🚀 Momentum Leaders", "🌍 Global (ex-US)",
             "🌏 Emerging Markets"],
            key="sc_view",
            help="Preset screens over the same scored universe. Top Value = "
                 "quality that's also cheap; Under the Radar = strong "
                 "fundamentals + cheap + quiet news; Momentum Leaders = "
                 "top 12-1 momentum; Global (ex-US) = both ADR sleeves "
                 "(developed + emerging); Emerging Markets = the EM sleeve "
                 "only.",
        )

        # ── Filtered screener table ───────────────────────────────────────────
        filtered = df_sc[
            df_sc["action"].isin(action_filter) & (df_sc["ai_score"] >= min_score)
        ]
        if sector_filter and "sector" in filtered.columns:
            filtered = filtered[filtered["sector"].isin(sector_filter)]
        filtered = filtered.sort_values("ai_score", ascending=False)

        if view == "⭐ Top Value" and "value_score" in filtered.columns:
            filtered = (filtered[filtered["value_score"].notna()
                                 & (filtered.get("fund_score", 0) >= 5.0)]
                        .sort_values("value_score", ascending=False).head(20))
        elif view == "💎 Under the Radar" and "under_radar" in filtered.columns:
            filtered = (filtered[filtered["under_radar"]]
                        .sort_values("value_score", ascending=False))
        elif view == "🚀 Momentum Leaders" and "mom_12m" in filtered.columns:
            filtered = (filtered[filtered["mom_12m"].notna()]
                        .sort_values("mom_12m", ascending=False).head(20))
        elif view == "🌍 Global (ex-US)" and "sleeve" in filtered.columns:
            # Both ADR sleeves. This view predates the em sleeve, when TSM/
            # BABA/MELI/etc all lived in `global` — filtering on "global"
            # alone silently dropped 25 names from a view whose whole point
            # is ex-US exposure.
            filtered = filtered[filtered["sleeve"].isin(["global", "em"])]
        elif view == "🌏 Emerging Markets" and "sleeve" in filtered.columns:
            filtered = filtered[filtered["sleeve"] == "em"]

        tbl_hdr = st.container()
        tbl_hdr.markdown(
            f'<div style="font-size:15px;font-weight:700;color:{TEXT_PRI};margin-bottom:12px;">'
            f'Screener Results — <span style="color:{ACCENT};">{len(filtered)}</span> stocks</div>',
            unsafe_allow_html=True,
        )

        if filtered.empty:
            st.info("No stocks match your current filters. Try lowering the minimum score or including more actions.")
        else:
            display_cols = [
                "ai_score", "action_badge", "sector", "last_price", "mom_12m",
                "tech_score", "sent_score", "fund_score", "value_score",
                "rsi", "sentiment_score", "pe_forward", "roe",
                "confidence_pct", "price_trend",
            ]
            disp = filtered[[c for c in display_cols if c in filtered.columns]].copy()
            if "mom_12m" in disp.columns:
                disp["mom_12m"] = disp["mom_12m"] * 100
            if "roe" in disp.columns:
                disp["roe"] = disp["roe"] * 100

            col_cfg = {
                "ai_score":        st.column_config.ProgressColumn(
                                       "AI Score", min_value=1, max_value=10, format="%.1f"),
                "action_badge":    st.column_config.TextColumn("Signal", width="small"),
                "sector":          st.column_config.TextColumn("Sector", width="small"),
                "last_price":      st.column_config.NumberColumn("Price", format="$%.2f"),
                "mom_12m":         st.column_config.NumberColumn("12M Return", format="%.1f%%"),
                "tech_score":      st.column_config.NumberColumn("Tech", format="%.1f",
                                       help="Technical layer sub-score (45% weight)"),
                "sent_score":      st.column_config.NumberColumn("News", format="%.1f",
                                       help="Sentiment layer sub-score (25% weight)"),
                "fund_score":      st.column_config.NumberColumn("Fund", format="%.1f",
                                       help="Fundamentals layer sub-score (30% weight)"),
                "value_score":     st.column_config.NumberColumn("Value", format="%.1f",
                                       help="Valuation-only lens (cheapness), 0–10 — "
                                            "not part of the AI Score blend. 💎 in the "
                                            "Signal column = strong fundamentals + cheap "
                                            "+ quiet news (under the radar)"),
                "rsi":             st.column_config.NumberColumn("RSI", format="%.0f"),
                "sentiment_score": st.column_config.ProgressColumn(
                                       "Sentiment", min_value=-1, max_value=1, format="%.3f"),
                "pe_forward":      st.column_config.NumberColumn("Fwd P/E", format="%.1f"),
                "roe":             st.column_config.NumberColumn("ROE", format="%.1f%%"),
                "confidence_pct":  st.column_config.ProgressColumn(
                                       "Confidence", min_value=0, max_value=100, format="%.0f%%"),
                "price_trend":     st.column_config.LineChartColumn(
                                       "3M Chart", y_min=None, y_max=None, width="medium"),
            }
            st.dataframe(disp, column_config=col_cfg, use_container_width=True,
                         height=min(700, len(disp) * 52 + 80))

        # ── AI Copilot ────────────────────────────────────────────────────────
        st.divider()
        st.markdown(
            f'<div style="font-size:15px;font-weight:700;color:{TEXT_PRI};margin-bottom:4px;">🤖 AI Copilot</div>'
            f'<div style="font-size:12px;color:{TEXT_SEC};margin-bottom:16px;">Answers are based strictly on today\'s computed signals — no outside knowledge used.</div>',
            unsafe_allow_html=True,
        )

        if not _HAS_OPENAI:
            st.info("Run `pip install openai` to enable the AI Copilot.")
        elif not OPENAI_KEY:
            st.info("Set `OPENAI_API_KEY` in your `.env` file to activate AI chat.")
        else:
            ctx_cols = ["ai_score", "action", "tech_score", "sent_score",
                        "fund_score", "last_price", "mom_12m", "rsi",
                        "sentiment_score", "pe_forward", "roe"]
            ctx_df = df_sc[[c for c in ctx_cols if c in df_sc.columns]]
            data_ctx = ctx_df.to_string(max_rows=80)
            system_prompt = (
                "You are a quantitative stock analysis assistant. "
                "Answer ONLY using the computed signal data below. "
                "Never use outside knowledge or general opinions. "
                "Always cite specific numbers from the table.\n\n"
                f"TODAY'S SIGNAL DATA ({px.index[-1].strftime('%Y-%m-%d')}):\n{data_ctx}"
            )

            if "ai_messages" not in st.session_state:
                st.session_state.ai_messages = []

            for msg in st.session_state.ai_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            if prompt := st.chat_input("Ask about any stock — e.g. 'Why is NVDA scoring high?' or 'What are the top 3 buys?'", key="ai_input"):
                st.session_state.ai_messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Analysing…"):
                        try:
                            client = OpenAI(api_key=OPENAI_KEY)
                            resp   = client.chat.completions.create(
                                model="gpt-4.1-mini",
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    *st.session_state.ai_messages,
                                ],
                                max_tokens=600, temperature=0.2,
                            )
                            reply = resp.choices[0].message.content
                            st.markdown(reply)
                            st.session_state.ai_messages.append(
                                {"role": "assistant", "content": reply}
                            )
                        except Exception as e:
                            st.error(f"AI error: {e}")

            if st.session_state.get("ai_messages"):
                if st.button("Clear chat", key="ai_clear"):
                    st.session_state.ai_messages = []
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
with tab_signals:
    st.subheader("Signal Book")
    st.caption("Stocks passing the entry filter today, with target weights.")

    c1, c2, c3 = st.columns([1, 1, 2])
    source   = c1.selectbox("Sentiment source", ["free", "alphavantage"],
                             index=0 if CFG.sentiment.source == "free" else 1, key="sig_src")
    use_sent = c2.toggle("Use sentiment", value=True, key="sig_usesent")
    run_sig  = c3.button("Refresh signals", key="sig_refresh")

    if run_sig or "sig_df" not in st.session_state:
        panels_sig = momentum.build_panels(px)
        today      = px.index[-1]
        sent_row   = pd.Series(0.0, index=px.columns)
        if use_sent and not offline:
            try:
                if source == "alphavantage":
                    from src import av_sentiment as av
                    snap = av.fetch_today(list(px.columns))
                    if not snap.empty:
                        av.append_sentiment_rows(snap, source="alphavantage")
                        sent_row = sent_mod.neutral_fill(
                            snap.set_index("ticker")["score"].reindex(px.columns))
                else:
                    snap     = sent_mod.fetch_all_sentiment(list(px.columns))
                    sent_mod.log_sentiment(snap, source="free")
                    sent_row = sent_mod.neutral_fill(
                        snap["score"].reindex(px.columns))
            except Exception as e:
                st.warning(f"Sentiment fetch failed ({e}); showing momentum-only.")

        w = signals.weights_for_date(
            today, px, panels_sig, sentiment=sent_row,
            use_sentiment=use_sent and not offline,
        )
        rows = [
            {
                "TICKER":    t,
                "SIDE":      "LONG" if w[t] > 0 else "SHORT" if w[t] < 0 else "—",
                "WGT%":      round(w[t] * 100, 1),
                "TSM 12M%":  round(panels_sig["tsm"][t].iloc[-1] * 100, 1),
                "52W RATIO": round(panels_sig["ratio52"][t].iloc[-1], 2),
                "RSI":       round(panels_sig["rsi"][t].iloc[-1], 1),
                "SENTIMENT": round(float(sent_row.get(t, 0.0)), 3),
            }
            for t in px.columns
        ]
        st.session_state.sig_df = pd.DataFrame(rows)

    df_sig = st.session_state.sig_df
    book   = df_sig[df_sig.SIDE != "—"]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Positions",     len(book))
    m2.metric("Longs",         len(book[book.SIDE == "LONG"]))
    m3.metric("Shorts",        len(book[book.SIDE == "SHORT"]))
    m4.metric("Avg Sentiment", f"{book['SENTIMENT'].mean():+.3f}" if len(book) else "0.000")
    m5.metric("Avg RSI",       f"{book['RSI'].mean():.0f}"        if len(book) else "—")

    if not book.empty:
        st.dataframe(book.sort_values("WGT%", ascending=False),
                     use_container_width=True, hide_index=True,
                     height=min(500, len(book) * 45 + 60))
    else:
        st.info("No names pass the filter today. Try adjusting RSI or 52W bands in CONFIG.")

    with st.expander("Full universe screen"):
        st.dataframe(df_sig, use_container_width=True, hide_index=True, height=500)


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
with tab_backtest:
    st.subheader("Historical Backtest")

    c1, c2, c3, c4 = st.columns(4)
    maxpos      = c1.number_input("Max positions", 1, 30, CFG.portfolio.max_positions, key="bt_maxpos")
    cost        = c2.number_input("Cost (bps)", 0.0, 100.0, CFG.portfolio.transaction_cost_bps, key="bt_cost")
    use_sent_bt = c3.toggle("Sentiment overlay", value=False, key="bt_sent",
                             help="Requires logged history (SENTIMENT tab).")
    run_bt      = c4.button("Run backtest", key="bt_run")

    if run_bt:
        CFG.portfolio.max_positions       = int(maxpos)
        CFG.portfolio.transaction_cost_bps = float(cost)
        with st.spinner("Running walk-forward…"):
            st.session_state.bt = bt_mod.run_backtest(px, bench, use_sentiment=use_sent_bt)

    if "bt" not in st.session_state:
        st.info("Set parameters above and click **Run backtest**.")
    else:
        res = st.session_state.bt
        m   = res.metrics
        act = m["active_return_pct"]

        r1, r2, r3, r4, r5, r6 = st.columns(6)
        r1.metric("CAGR",      f"{m['cagr_pct']:.2f}%",     f"bench {m['benchmark_cagr_pct']:.2f}%")
        r2.metric("Active",    f"{act:+.2f}%",              "vs benchmark")
        r3.metric("Sharpe",    f"{m['sharpe']:.2f}",        "ann · daily MTM")
        r4.metric("Sortino",   f"{m['sortino']:.2f}")
        r5.metric("Calmar",    f"{m['calmar']:.2f}")
        r6.metric("Max DD",    f"{m['max_drawdown_pct']:.1f}%")

        r7, r8, r9, r10, r11, r12 = st.columns(6)
        r7.metric("Vol",        f"{m['ann_vol_pct']:.1f}%",     "annualised")
        r8.metric("Beta",       f"{m.get('beta', 0):.2f}",      "vs benchmark")
        r9.metric("Alpha",      f"{m.get('alpha_ann_pct', 0):+.2f}%", "annualised")
        r10.metric("Info Ratio", f"{m.get('information_ratio', 0):.2f}")
        r11.metric("Win Rate",  f"{m['win_rate_pct']:.0f}%",    f"{m['n_trades']} trades")
        r12.metric("Avg Trade", f"{m['avg_trade_pct']:+.2f}%",  f"{m['avg_hold_days']}d hold")

        fig_eq = go.Figure()
        fig_eq.add_scatter(x=res.equity.index, y=res.equity,
                           name="Strategy",  line=dict(color=P_ACCENT, width=2.5))
        fig_eq.add_scatter(x=res.benchmark.index, y=res.benchmark,
                           name="Benchmark", line=dict(color=P_MUTED, width=1.8, dash="dot"))
        fig_eq.update_layout(title=dict(text="Portfolio Equity (£)", font=dict(size=14)))
        st.plotly_chart(_theme(fig_eq), use_container_width=True)

        col_a, col_b = st.columns(2)

        dd = (res.equity / res.equity.cummax() - 1) * 100
        fig_dd = go.Figure()
        fig_dd.add_scatter(x=dd.index, y=dd, fill="tozeroy", name="Drawdown",
                           line=dict(color=P_DANGER, width=1.5),
                           fillcolor="rgba(239,68,68,0.12)")
        fig_dd.update_layout(title=dict(text="Drawdown (%)", font=dict(size=14)))
        col_a.plotly_chart(_theme(fig_dd, 260), use_container_width=True)

        mo   = res.daily_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
        df_m = mo.to_frame("r")
        df_m["Y"] = df_m.index.year
        df_m["M"] = df_m.index.month
        grid = df_m.pivot_table(index="Y", columns="M", values="r")
        lim  = np.nanmax(np.abs(grid.values)) if grid.size else 1
        fig_hm = go.Figure(go.Heatmap(
            z=grid.values, x=[f"{c:02d}" for c in grid.columns], y=grid.index.astype(str),
            colorscale=[[0, P_DANGER], [0.5, "#F8FAFC"], [1, P_SUCCESS]],
            zmid=0, zmin=-lim, zmax=lim,
            text=np.round(grid.values, 1), texttemplate="%{text}",
            textfont=dict(size=10), colorbar=dict(thickness=12),
        ))
        fig_hm.update_layout(title=dict(text="Monthly Returns (%)", font=dict(size=14)))
        col_b.plotly_chart(_theme(fig_hm, 60 + 28 * len(grid)), use_container_width=True)

        if res.walk_forward:
            st.subheader("Walk-Forward · Out-of-Sample")
            wf = pd.DataFrame(res.walk_forward)
            wf.columns = ["Window", "In CAGR%", "Out CAGR%", "Out Bench%"]
            st.dataframe(wf, use_container_width=True, hide_index=True)

        st.subheader("Trade Blotter")
        st.dataframe(res.trades, use_container_width=True, hide_index=True, height=300)
        st.download_button("Download trade log (CSV)", res.trades.to_csv(index=False),
                           "trade_log.csv", "text/csv", key="bt_dl")


# ─────────────────────────────────────────────────────────────────────────────
# SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────
with tab_sentiment:
    st.subheader("Sentiment Data")
    st.caption("Free news is recent-only. Alpha Vantage reaches ~2022+. "
               "Fetches accumulate into data/sentiment_history.csv for backtests.")

    c1, c2, c3 = st.columns(3)
    if c1.button("Fetch free (today)", key="se_free") and not offline:
        with st.spinner("Scoring RSS + yfinance headlines…"):
            try:
                snap = sent_mod.fetch_all_sentiment(list(px.columns))
                sent_mod.log_sentiment(snap, source="free")
                st.success(f"Logged {len(snap)} free scores.")
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    start_av = c2.date_input("AV history from", pd.Timestamp("2022-03-01"),
                              key="se_from").strftime("%Y-%m-%d")
    if c3.button("Fetch Alpha Vantage", key="se_av") and not offline:
        with st.spinner("Pulling Alpha Vantage history (≤25/day free)…"):
            try:
                from src import av_sentiment as av
                got = av.fetch_history(list(px.columns), start_av, CFG.universe.end_date)
                st.success(f"Fetched {0 if got is None else len(got)} daily rows "
                           "(cached; re-run tomorrow for the rest).")
            except Exception as e:
                st.error(f"Alpha Vantage failed: {e}")

    p_sent = Path(CFG.paths.sentiment_log)
    if not p_sent.exists():
        st.info("No sentiment logged yet. Use the fetch buttons above.")
    else:
        hist = pd.read_csv(p_sent, parse_dates=["date"])
        if "source" not in hist.columns:
            hist["source"] = "free"
        by_src = hist.groupby("source").agg(
            rows=("score", "size"), tickers=("ticker", "nunique"),
            first=("date", "min"), last=("date", "max"),
        )
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Total rows", f"{len(hist):,}")
        r2.metric("Tickers",    hist.ticker.nunique())
        r3.metric("From",       f"{hist.date.min():%Y-%m-%d}")
        r4.metric("To",         f"{hist.date.max():%Y-%m-%d}")
        st.dataframe(by_src.reset_index(), use_container_width=True, hide_index=True)

        tk = st.selectbox("Inspect ticker", sorted(hist.ticker.unique()), key="se_tk")
        series = hist[hist.ticker == tk].sort_values("date")
        fig_s = go.Figure()
        fig_s.add_scatter(x=series.date, y=series.score, mode="lines+markers",
                          line=dict(color=P_ACCENT, width=1.8), marker=dict(size=4), name=tk)
        fig_s.add_hline(y=0, line=dict(color=P_MUTED, width=1, dash="dot"))
        fig_s.update_layout(title=dict(text=f"{tk} — Sentiment History", font=dict(size=14)))
        st.plotly_chart(_theme(fig_s, 300), use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
with tab_config:
    st.subheader("Signal Parameters — Live Session")
    st.caption("Tunes this session's signals/backtests. For permanent defaults edit config.py.")

    sc = CFG.signal
    c1, c2, c3 = st.columns(3)
    sc.trend_tsm_min         = c1.number_input("Min 12M return", -1.0, 1.0, sc.trend_tsm_min, 0.01, key="cf_tsm")
    sc.near_floor_52w        = c1.slider("52W floor", 0.0, 1.0, sc.near_floor_52w, 0.01, key="cf_52w")
    sc.require_above_long_ma = c1.toggle("Require > long MA", value=sc.require_above_long_ma, key="cf_ma")
    sc.rsi_pullback_min      = c2.slider("RSI pullback min", 0.0, 60.0, sc.rsi_pullback_min, key="cf_rsimin")
    sc.rsi_pullback_max      = c2.slider("RSI pullback max", 20.0, 80.0, sc.rsi_pullback_max, key="cf_rsimax")
    sc.long_sentiment_min    = c2.number_input("Min sentiment", -1.0, 1.0, sc.long_sentiment_min, 0.01, key="cf_sent")
    sc.enable_shorts         = c3.toggle("Enable shorts", value=sc.enable_shorts, key="cf_short")
    sc.rank_sentiment_weight = c3.slider("Sentiment rank weight", 0.0, 1.0,
                                          sc.rank_sentiment_weight, 0.05, key="cf_rankw")
    CFG.portfolio.use_inverse_vol_weights = c3.toggle(
        "Inverse-vol sizing", value=CFG.portfolio.use_inverse_vol_weights, key="cf_ivol",
        help="Size longs ∝ 1/realised vol instead of equal weight.",
    )
    CFG.momentum.regime_method = c3.selectbox(
        "Regime detector", ["breadth", "hmm"],
        index=0 if CFG.momentum.regime_method == "breadth" else 1, key="cf_regime",
        help="breadth = fraction of universe above long MA (default). "
             "hmm = 3-state Gaussian HMM, walk-forward refit (needs hmmlearn; "
             "falls back to breadth if missing). Applies to the next backtest run.",
    )
    CFG.portfolio.max_positions = c3.number_input(
        "Max positions", 1, 30, CFG.portfolio.max_positions, key="cf_maxpos"
    )
    st.info(
        f"**Active LONG rule** — 12M return > `{sc.trend_tsm_min}` · "
        f"52W ratio ≥ `{sc.near_floor_52w}` · "
        f"{'price > long MA · ' if sc.require_above_long_ma else ''}"
        f"RSI ∈ [`{sc.rsi_pullback_min:.0f}`, `{sc.rsi_pullback_max:.0f}`] · "
        f"sentiment ≥ `{sc.long_sentiment_min}`"
    )


st.caption(
    f"Stock Picker AI · {len(CFG.universe.tickers)} stocks · "
    f"free data (yfinance · RSS · Alpha Vantage) · "
    f"research tool, not investment advice"
)
