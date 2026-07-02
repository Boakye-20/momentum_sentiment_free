"""
dashboard.py — modern dev/fintech control panel for the strategy
(deep-slate dark theme in the spirit of Linear / Vercel / Supabase).

    pip install -r requirements.txt
    python -m streamlit run dashboard.py

Opens at http://localhost:8501. Four function panels:
  SIGNALS   today's momentum + sentiment book
  BACKTEST  historical run, metrics, equity/drawdown/heatmap, trade log
  SENTIMENT logged sentiment history + fetch controls (free / Alpha Vantage)
  CONFIG    live-tune the entry rules

Everything runs locally on free data. Use the "OFFLINE DEMO" toggle to explore
the UI with synthetic prices when you have no network.
"""

from __future__ import annotations
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CFG
from src import data as data_mod
from src import momentum, signals
from src import sentiment as sent_mod
from src import backtest as bt_mod

# ── palette (modern dev / fintech dark — deep slate, not pure black) ──────
BG      = "#101419"   # app background
PANEL   = "#151a21"   # raised surface (one background step up)
PANEL2  = "#1b212b"   # hover / second step
LINE    = "#232b36"   # 1px separators
GRID    = "#1d232d"   # chart gridlines (softer than LINE)
TEXT    = "#dce3ec"   # muted off-white body text
BRIGHT  = "#f2f5f9"   # headings / primary values
MUTED   = "#8a94a3"   # labels, captions, secondary text
GREEN   = "#3fb950"   # gains / risk-on   — data & status only
RED     = "#f85149"   # losses / risk-off — data & status only
AMBER   = "#e8a33d"   # strategy series / neutral status — data & status only

st.set_page_config(page_title="MOMENTUM·SENTIMENT TERMINAL",
                   page_icon="◢", layout="wide",
                   initial_sidebar_state="collapsed")


# ──────────────────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root, html, body, [class*="css"] { font-family:'Inter',system-ui,sans-serif !important; }
.stApp { background:#101419; color:#dce3ec; }
#MainMenu, header, footer { visibility:hidden; }
.block-container { padding:1rem 1.6rem 2rem 1.6rem; max-width:100%; }

/* command bar — flat surface, 1px border */
.cmdbar { background:#151a21; border:1px solid #232b36; border-radius:4px;
  padding:10px 16px; display:flex; align-items:center; gap:16px; margin-bottom:16px; }
.cmdbar .brand { color:#f2f5f9; font-weight:600; letter-spacing:0.4px; font-size:15px; }
.cmdbar .tag { color:#8a94a3; font-size:11px; font-family:'JetBrains Mono',monospace;
  letter-spacing:0.4px; }
.cmdbar .spacer { flex:1; }
.pill { padding:3px 10px; border:1px solid #232b36; font-size:11px; font-weight:500;
  color:#8a94a3; background:#101419; border-radius:4px;
  font-family:'JetBrains Mono',monospace; letter-spacing:0.4px;
  display:inline-flex; align-items:center; }
.pill::before { content:""; width:6px; height:6px; border-radius:50%;
  background:currentColor; margin-right:7px; }
.pill.on    { border-color:#274531; color:#3fb950; background:#131b16; }
.pill.off   { border-color:#4c2a29; color:#f85149; background:#1c1416; }
.pill.amber { border-color:#4a3a20; color:#e8a33d; background:#1a1712; }

/* stat cells */
.kpiwrap { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:10px; margin:10px 0 18px 0; }
.kpi { background:#151a21; padding:14px 16px; border:1px solid #232b36;
  border-radius:4px; }
.kpi .lab { color:#8a94a3; font-size:11px; font-weight:500; letter-spacing:0.8px;
  text-transform:uppercase; }
.kpi .val { font-size:22px; font-weight:600; margin-top:6px; color:#f2f5f9;
  font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; }
.kpi .sub { font-size:11px; color:#8a94a3; margin-top:3px; }
.up { color:#3fb950 !important; } .down { color:#f85149 !important; }
.amber { color:#e8a33d !important; }

/* table */
.tt { width:100%; border-collapse:collapse; font-size:13px; }
.tt th { background:#151a21; color:#8a94a3; text-align:right; padding:9px 14px;
  font-weight:500; border-bottom:1px solid #232b36; font-size:11px;
  letter-spacing:0.7px; text-transform:uppercase; }
.tt th:first-child, .tt td:first-child { text-align:left; }
.tt td { padding:8px 14px; text-align:right; border-bottom:1px solid #1a2029;
  color:#dce3ec; font-family:'JetBrains Mono',monospace;
  font-variant-numeric:tabular-nums; }
.tt tr:hover td { background:#1b212b; }
.tt .tk { color:#f2f5f9; font-weight:600; }
.sec { color:#8a94a3; font-size:11px; font-weight:600; letter-spacing:1px;
  text-transform:uppercase; border-bottom:1px solid #232b36;
  padding-bottom:8px; margin:18px 0 14px 0; }

/* tabs — underline selection, no filled blocks */
.stTabs [data-baseweb="tab-list"] { gap:2px; background:transparent;
  border-bottom:1px solid #232b36; }
.stTabs [data-baseweb="tab"] { background:transparent; color:#8a94a3;
  border-radius:4px 4px 0 0; padding:9px 18px; font-size:13px; font-weight:500; }
.stTabs [data-baseweb="tab"]:hover { color:#dce3ec; background:#151a21; }
.stTabs [aria-selected="true"] { background:transparent; color:#f2f5f9 !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color:#f2f5f9 !important; }
.stTabs [data-baseweb="tab-border"] { background-color:#232b36 !important; }

/* widgets */
.stButton>button { background:#1b212b; color:#f2f5f9; border:1px solid #2c3542;
  border-radius:4px; font-weight:500; font-size:13px; padding:6px 18px; }
.stButton>button:hover { background:#232b36; border-color:#3a4656; color:#ffffff; }
.stDataFrame { border:1px solid #232b36; border-radius:4px; }
div[data-baseweb="select"]>div, .stNumberInput input, .stDateInput input {
  background:#151a21 !important; border-color:#232b36 !important;
  border-radius:4px !important; color:#dce3ec !important; }
[data-testid="stNumberInput"] button {
  background:#1b212b !important; color:#dce3ec !important;
  border-color:#232b36 !important; }
[data-testid="stNumberInput"] > div, [data-testid="stDateInput"] > div {
  border-radius:4px !important; }
.foot { color:#8a94a3; font-size:12px; border-top:1px solid #232b36;
  padding-top:10px; margin-top:18px; }
.stCaption, [data-testid="stCaptionContainer"] p { color:#8a94a3 !important; }
.stAlert p, .stInfo p { color:#dce3ec !important; }
label, .stMarkdown p, .stMarkdown li,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] *,
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"],
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"],
.stSlider [data-testid="stThumbValue"], .stSlider label p,
[data-testid="stHeader"], [data-testid="stHeadingWithActionElements"] *,
.stExpander summary, .stExpander summary p, .stExpander svg,
[data-testid="stNumberInputLabel"] {
  color:#dce3ec !important; }
[data-testid="stSidebar"] { background:#151a21; border-right:1px solid #232b36; }
.stSidebar, [data-testid="stSidebar"], .stSidebar * { color:#dce3ec !important; }
[data-testid="stTooltipIcon"], [data-testid="stTooltipIcon"] svg,
[data-testid="stTooltipHoverTarget"], [data-testid="stTooltipHoverTarget"] svg,
[data-testid="stTooltipIcon"] *, [data-testid="stTooltipHoverTarget"] * {
  color:#8a94a3 !important; fill:#8a94a3 !important; opacity:1 !important; }
div[data-baseweb="tooltip"], div[data-baseweb="tooltip"] * {
  color:#dce3ec !important; background:#1b212b !important; }
</style>
""", unsafe_allow_html=True)


def header_bar(regime: str, source: str, offline: bool):
    rcolor = {"risk_on": "on", "risk_off": "off", "neutral": "amber"}.get(regime, "amber")
    st.markdown(f"""
<div class="cmdbar">
  <span class="brand">◢ MOMENTUM·SENTIMENT</span>
  <span class="tag">TERMINAL v1.0</span>
  <span class="spacer"></span>
  <span class="pill {rcolor}">REGIME {regime.upper()}</span>
  <span class="pill amber">SRC {source.upper()}</span>
  <span class="pill {'off' if offline else 'on'}">{'OFFLINE DEMO' if offline else 'LIVE DATA'}</span>
  <span class="tag">{datetime.now():%Y-%m-%d %H:%M:%S}</span>
</div>""", unsafe_allow_html=True)


def kpi_row(items):
    cells = "".join(
        f'<div class="kpi"><div class="lab">{lab}</div>'
        f'<div class="val {tone}">{val}</div>'
        f'<div class="sub">{sub}</div></div>'
        for lab, val, sub, tone in items)
    st.markdown(f'<div class="kpiwrap">{cells}</div>', unsafe_allow_html=True)


def sgn(x):  # tone class by sign
    return "up" if x > 0 else "down" if x < 0 else ""


# ── plotly dark theme ─────────────────────────────────────────────────────
def _theme(fig, h=360):
    fig.update_layout(
        template="plotly_dark", height=h, paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(family="Inter, system-ui, sans-serif", color=TEXT, size=12),
        margin=dict(l=55, r=20, t=40, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified")
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, showline=True,
                     linecolor=LINE, tickfont=dict(size=11, color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, showline=True,
                     linecolor=LINE, tickfont=dict(size=11, color=MUTED))
    return fig


def plot_equity(res):
    fig = go.Figure()
    fig.add_scatter(x=res.equity.index, y=res.equity, name="Strategy",
                    line=dict(color=AMBER, width=2.2))
    fig.add_scatter(x=res.benchmark.index, y=res.benchmark, name="Benchmark",
                    line=dict(color=MUTED, width=1.6, dash="dot"))
    fig.update_layout(title=dict(text="Portfolio Equity (£)", font=dict(color=TEXT, size=14)))
    return _theme(fig)


def plot_drawdown(res):
    dd = (res.equity / res.equity.cummax() - 1) * 100
    fig = go.Figure()
    fig.add_scatter(x=dd.index, y=dd, fill="tozeroy", name="Drawdown",
                    line=dict(color=RED, width=1.5), fillcolor="rgba(248,81,73,0.18)")
    fig.update_layout(title=dict(text="Drawdown (%)", font=dict(color=TEXT, size=14)))
    return _theme(fig, 260)


def plot_monthly(res):
    m = res.daily_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    df = m.to_frame("r")
    df["Y"] = df.index.year
    df["M"] = df.index.month
    grid = df.pivot_table(index="Y", columns="M", values="r")
    lim = np.nanmax(np.abs(grid.values)) if grid.size else 1
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=[f"{c:02d}" for c in grid.columns], y=grid.index.astype(str),
        colorscale=[[0, RED], [0.5, PANEL], [1, GREEN]], zmid=0, zmin=-lim, zmax=lim,
        text=np.round(grid.values, 1), texttemplate="%{text}",
        textfont=dict(size=10), colorbar=dict(thickness=12)))
    fig.update_layout(title=dict(text="Monthly Returns (%)", font=dict(color=TEXT, size=14)))
    return _theme(fig, 60 + 28 * len(grid))


# ── data helpers (cached) ─────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_prices(offline: bool, start: str, end: str):
    src = "synthetic" if offline else "yfinance"
    allp = data_mod.load_prices(start=start, end=end, source=src,
                                use_cache=not offline)
    px, bench = data_mod.split_universe_benchmark(allp)
    if bench is None:
        bench = px.mean(axis=1)
    return px, bench


def current_regime(px):
    try:
        return momentum.breadth_regime(px).iloc[-1]
    except Exception:
        return "neutral"


# ──────────────────────────────────────────────────────────────────────────
# Panels
# ──────────────────────────────────────────────────────────────────────────
def panel_signals(px, offline):
    st.markdown('<div class="sec">TODAY · SIGNAL BOOK</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 4])
    source = c1.selectbox("SENTIMENT SOURCE", ["free", "alphavantage"],
                          index=0 if CFG.sentiment.source == "free" else 1, key="sig_src")
    use_sent = c2.toggle("USE SENTIMENT", value=True, key="sig_usesent")
    run = c3.button("REFRESH SIGNALS", width='stretch', key="sig_refresh")

    if run or "sig_df" not in st.session_state:
        panels = momentum.build_panels(px)
        today = px.index[-1]
        sent_row = pd.Series(0.0, index=px.columns)
        if use_sent and not offline:
            try:
                if source == "alphavantage":
                    from src import av_sentiment as av
                    snap = av.fetch_today(list(px.columns))
                    if not snap.empty:
                        av.append_sentiment_rows(snap, source="alphavantage")
                        sent_row = snap.set_index("ticker")["score"].reindex(px.columns).fillna(0)
                else:
                    snap = sent_mod.fetch_all_sentiment(list(px.columns))
                    sent_mod.log_sentiment(snap, source="free")
                    sent_row = snap["score"].reindex(px.columns).fillna(0)
            except Exception as e:
                st.warning(f"Sentiment fetch failed ({e}); showing momentum-only.")
        w = signals.weights_for_date(today, px, panels, sentiment=sent_row,
                                     use_sentiment=use_sent and not offline)
        rows = []
        for t in px.columns:
            rows.append({"TICKER": t,
                         "SIDE": "LONG" if w[t] > 0 else "SHORT" if w[t] < 0 else "—",
                         "WGT%": round(w[t] * 100, 1),
                         "TSM12M%": round(panels["tsm"][t].iloc[-1] * 100, 1),
                         "52W": round(panels["ratio52"][t].iloc[-1], 2),
                         "RSI": round(panels["rsi"][t].iloc[-1], 1),
                         "SENT": round(float(sent_row.get(t, 0.0)), 3)})
        st.session_state.sig_df = pd.DataFrame(rows)

    df = st.session_state.sig_df
    book = df[df.SIDE != "—"]
    longs = book[book.SIDE == "LONG"]
    shorts = book[book.SIDE == "SHORT"]
    kpi_row([
        ("POSITIONS", f"{len(book)}", f"of {len(df)} screened", "amber"),
        ("LONGS", f"{len(longs)}", "", "up"),
        ("SHORTS", f"{len(shorts)}", "", "down" if len(shorts) else ""),
        ("AVG SENT", f"{book.SENT.mean():+.3f}" if len(book) else "0.000", "book mean",
         sgn(book.SENT.mean() if len(book) else 0)),
        ("AVG RSI", f"{book.RSI.mean():.0f}" if len(book) else "—", "", ""),
    ])

    # held book as terminal table
    if len(book):
        rowhtml = ""
        for _, r in book.sort_values("WGT%", ascending=False).iterrows():
            sd = "up" if r.SIDE == "LONG" else "down"
            rowhtml += (f'<tr><td class="tk">{r.TICKER}</td>'
                        f'<td class="{sd}">{r.SIDE}</td><td>{r["WGT%"]:.1f}</td>'
                        f'<td class="{sgn(r["TSM12M%"])}">{r["TSM12M%"]:+.1f}</td>'
                        f'<td>{r["52W"]:.2f}</td><td>{r.RSI:.1f}</td>'
                        f'<td class="{sgn(r.SENT)}">{r.SENT:+.3f}</td></tr>')
        st.markdown(
            '<table class="tt"><tr><th>TICKER</th><th>SIDE</th><th>WGT%</th>'
            '<th>TSM 12M%</th><th>52W</th><th>RSI</th><th>SENT</th></tr>'
            + rowhtml + "</table>", unsafe_allow_html=True)
    else:
        st.info("No names pass the filter today. Loosen RSI/52W band in CONFIG.")

    with st.expander("FULL UNIVERSE SCREEN"):
        st.dataframe(df, width='stretch', hide_index=True, height=420)


def panel_backtest(px, bench, offline):
    st.markdown('<div class="sec">HISTORICAL BACKTEST</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    maxpos = c1.number_input("MAX POSITIONS", 1, 30, CFG.portfolio.max_positions, key="bt_maxpos")
    cost = c2.number_input("COST (BPS)", 0.0, 100.0, CFG.portfolio.transaction_cost_bps, key="bt_cost")
    use_sent = c3.toggle("SENTIMENT OVERLAY", value=False, key="bt_sent",
                         help="Requires logged history (SENTIMENT tab).")
    run = c4.button("RUN BACKTEST", width='stretch', key="bt_run")

    if run:
        CFG.portfolio.max_positions = int(maxpos)
        CFG.portfolio.transaction_cost_bps = float(cost)
        with st.spinner("running walk-forward ..."):
            st.session_state.bt = bt_mod.run_backtest(px, bench, use_sentiment=use_sent)

    if "bt" not in st.session_state:
        st.info("Set parameters and hit RUN BACKTEST.")
        return
    res = st.session_state.bt
    m = res.metrics
    act = m["active_return_pct"]
    kpi_row([
        ("CAGR", f"{m['cagr_pct']:.2f}%", f"bench {m['benchmark_cagr_pct']:.2f}%",
         sgn(m['cagr_pct'])),
        ("ACTIVE", f"{act:+.2f}%", "vs benchmark", sgn(act)),
        ("SHARPE", f"{m['sharpe']:.2f}", "ann · daily MTM", sgn(m['sharpe'])),
        ("SORTINO", f"{m['sortino']:.2f}", "", sgn(m['sortino'])),
        ("MAX DD", f"{m['max_drawdown_pct']:.1f}%", "", "down"),
        ("VOL", f"{m['ann_vol_pct']:.1f}%", "annualised", ""),
        ("WIN", f"{m['win_rate_pct']:.0f}%", f"{m['n_trades']} trades", sgn(m['win_rate_pct']-50)),
        ("AVG TRD", f"{m['avg_trade_pct']:+.2f}%", f"{m['avg_hold_days']}d hold",
         sgn(m['avg_trade_pct'])),
    ])
    st.plotly_chart(plot_equity(res), width='stretch')
    a, b = st.columns(2)
    a.plotly_chart(plot_drawdown(res), width='stretch')
    b.plotly_chart(plot_monthly(res), width='stretch')

    st.markdown('<div class="sec">WALK-FORWARD · OUT-OF-SAMPLE</div>', unsafe_allow_html=True)
    if res.walk_forward:
        wf = pd.DataFrame(res.walk_forward)
        wf.columns = ["WINDOW", "IN CAGR%", "OUT CAGR%", "OUT BENCH%"]
        st.dataframe(wf, width='stretch', hide_index=True)

    st.markdown('<div class="sec">TRADE BLOTTER</div>', unsafe_allow_html=True)
    st.dataframe(res.trades, width='stretch', hide_index=True, height=300)
    st.download_button("DOWNLOAD TRADE LOG (CSV)",
                       res.trades.to_csv(index=False), "trade_log.csv", "text/csv", key="bt_dl")


def panel_sentiment(px, offline):
    st.markdown('<div class="sec">SENTIMENT DATA</div>', unsafe_allow_html=True)
    st.caption("Free news is recent-only. Alpha Vantage reaches ~2022+. "
               "Fetch accumulates into data/sentiment_history.csv for backtests.")
    c1, c2, c3 = st.columns(3)
    if c1.button("FETCH FREE (TODAY)", width='stretch', key="se_free") and not offline:
        with st.spinner("scoring RSS + yfinance headlines ..."):
            try:
                snap = sent_mod.fetch_all_sentiment(list(px.columns))
                sent_mod.log_sentiment(snap, source="free")
                st.success(f"Logged {len(snap)} free scores.")
            except Exception as e:
                st.error(f"Fetch failed: {e}")
    start = c2.date_input("AV HISTORY FROM", pd.Timestamp("2022-03-01"), key="se_from").strftime("%Y-%m-%d")
    if c3.button("FETCH ALPHA VANTAGE", width='stretch', key="se_av") and not offline:
        with st.spinner("pulling Alpha Vantage history (≤25/day free) ..."):
            try:
                from src import av_sentiment as av
                got = av.fetch_history(list(px.columns), start, CFG.universe.end_date)
                st.success(f"Fetched {0 if got is None else len(got)} daily rows "
                           "(cached; re-run tomorrow for the rest).")
            except Exception as e:
                st.error(f"Alpha Vantage failed: {e}")

    # coverage
    from pathlib import Path
    p = Path(CFG.paths.sentiment_log)
    if not p.exists():
        st.info("No sentiment logged yet. Use the fetch buttons above.")
        return
    hist = pd.read_csv(p, parse_dates=["date"])
    if "source" not in hist.columns:
        hist["source"] = "free"
    by_src = hist.groupby("source").agg(rows=("score", "size"),
                                        tickers=("ticker", "nunique"),
                                        first=("date", "min"), last=("date", "max"))
    kpi_row([
        ("TOTAL ROWS", f"{len(hist):,}", "logged", "amber"),
        ("TICKERS", f"{hist.ticker.nunique()}", "", ""),
        ("FROM", f"{hist.date.min():%Y-%m-%d}", "", ""),
        ("TO", f"{hist.date.max():%Y-%m-%d}", "", ""),
        ("SOURCES", f"{hist.source.nunique()}", ", ".join(by_src.index), ""),
    ])
    st.dataframe(by_src.reset_index(), width='stretch', hide_index=True)

    tk = st.selectbox("INSPECT TICKER", sorted(hist.ticker.unique()), key="se_tk")
    series = hist[hist.ticker == tk].sort_values("date")
    fig = go.Figure()
    fig.add_scatter(x=series.date, y=series.score, mode="lines+markers",
                    line=dict(color=AMBER, width=1.4), marker=dict(size=4),
                    name=tk)
    fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
    fig.update_layout(title=dict(text=f"{tk} — Sentiment History", font=dict(color=TEXT, size=14)))
    st.plotly_chart(_theme(fig, 300), width='stretch')


def panel_config():
    st.markdown('<div class="sec">SIGNAL PARAMETERS · LIVE SESSION</div>', unsafe_allow_html=True)
    st.caption("Tunes this session's signals/backtests. For permanent defaults edit config.py.")
    sc = CFG.signal
    c1, c2, c3 = st.columns(3)
    sc.trend_tsm_min = c1.number_input("TREND · MIN 12M RETURN", -1.0, 1.0, sc.trend_tsm_min, 0.01, key="cf_tsm")
    sc.near_floor_52w = c1.slider("TREND · 52W FLOOR", 0.0, 1.0, sc.near_floor_52w, 0.01, key="cf_52w")
    sc.require_above_long_ma = c1.toggle("REQUIRE > LONG MA", value=sc.require_above_long_ma, key="cf_ma")
    sc.rsi_pullback_min = c2.slider("RSI PULLBACK · MIN", 0.0, 60.0, sc.rsi_pullback_min, key="cf_rsimin")
    sc.rsi_pullback_max = c2.slider("RSI PULLBACK · MAX", 20.0, 80.0, sc.rsi_pullback_max, key="cf_rsimax")
    sc.long_sentiment_min = c2.number_input("LONG · MIN SENTIMENT", -1.0, 1.0, sc.long_sentiment_min, 0.01, key="cf_sent")
    sc.enable_shorts = c3.toggle("ENABLE SHORTS", value=sc.enable_shorts, key="cf_short")
    sc.rank_sentiment_weight = c3.slider("RANK · SENTIMENT WEIGHT", 0.0, 1.0, sc.rank_sentiment_weight, 0.05, key="cf_rankw")
    CFG.portfolio.use_inverse_vol_weights = c3.toggle(
        "INVERSE-VOL SIZING", value=CFG.portfolio.use_inverse_vol_weights, key="cf_ivol",
        help="Size longs ∝ 1/realised vol instead of equal weight.")
    CFG.portfolio.max_positions = c3.number_input("MAX POSITIONS", 1, 30, CFG.portfolio.max_positions, key="cf_maxpos")
    st.markdown("**ACTIVE LONG RULE** — 12M return > "
                f"`{sc.trend_tsm_min}` · 52W ratio ≥ `{sc.near_floor_52w}` · "
                f"{'price > long MA · ' if sc.require_above_long_ma else ''}"
                f"RSI ∈ [`{sc.rsi_pullback_min:.0f}`,`{sc.rsi_pullback_max:.0f}`] · "
                f"sentiment ≥ `{sc.long_sentiment_min}`")


# ──────────────────────────────────────────────────────────────────────────
def main():
    inject_css()
    top = st.container()
    offline = st.sidebar.toggle("OFFLINE DEMO (synthetic prices)", value=False, key="sb_offline")
    start = st.sidebar.text_input("DATA START", CFG.universe.start_date, key="sb_start")
    end = st.sidebar.text_input("DATA END", CFG.universe.end_date, key="sb_end")

    try:
        px, bench = get_prices(offline, start, end)
        load_err = None
    except Exception as e:
        px, bench, load_err = None, None, str(e)

    with top:
        regime = current_regime(px) if px is not None else "neutral"
        header_bar(regime, CFG.sentiment.source, offline)

    if load_err:
        st.error(f"Price load failed: {load_err}\n\nTip: enable OFFLINE DEMO in the "
                 "sidebar to explore the terminal without network access.")
        return

    t1, t2, t3, t4 = st.tabs(["SIGNALS", "BACKTEST", "SENTIMENT", "CONFIG"])
    with t1:
        panel_signals(px, offline)
    with t2:
        panel_backtest(px, bench, offline)
    with t3:
        panel_sentiment(px, offline)
    with t4:
        panel_config()

    st.markdown(
        f'<div class="foot">MOMENTUM·SENTIMENT TERMINAL — free data (yfinance · '
        f'RSS · Alpha Vantage) — research tool, not investment advice — '
        f'universe {len(CFG.universe.tickers)} · benchmark {CFG.universe.benchmark_ticker}'
        f'</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
