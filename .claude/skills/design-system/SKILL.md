---
name: design-system
description: NextAdmin-style light design system for the Streamlit dashboard — colors, spacing, card patterns, sparklines, and Streamlit-specific styling rules. Load before any visual work on dashboard.py.
---

# Design System — NextAdmin Light

The whole app (every page and tab) follows the NextAdmin / TailAdmin visual
language: white surfaces on a soft blue-gray canvas, indigo accent, generous
rounded corners, soft shadows. Reference: NextAdmin stocks dashboard.

## Tokens (mirror of the constants at the top of dashboard.py)

| Token | Value | Use |
|---|---|---|
| ACCENT | `#6366F1` | buttons, active tab/nav, links, progress bars |
| ACCENT_SOFT | `#EEF2FF` | icon chips, active-nav background, tags |
| SUCCESS | `#22C55E` | gains, BUY, up-sparklines ONLY |
| DANGER | `#EF4444` | losses, AVOID, down-sparklines ONLY |
| WARNING | `#F59E0B` | HOLD, cautions |
| APP_BG | `#F5F7FB` | page canvas |
| CARD_BG | `#FFFFFF` | every card/panel/table surface |
| BORDER | `#E8ECF4` | 1px borders everywhere |
| TEXT_PRI | `#1C2434` | headings, values |
| TEXT_SEC | `#64748B` | body/secondary |
| MUTED | `#8A99AF` | labels, captions, section headers |

Green/red are data colors only — never chrome or decoration.

## Structure rules

- **Sidebar is WHITE** (NextAdmin), themed natively via `[theme.sidebar]` in
  `.streamlit/config.toml` — never re-style sidebar widgets with CSS testid
  hacks; that's what made it unreadable once.
- Border-radius: 16px cards/tables, 12px inner elements, 9px inputs/buttons,
  50% (circle) for logo chips.
- Shadows: soft and subtle — `0 1px 3px rgba(16,24,40,0.05)` on cards,
  slightly stronger indigo glow on primary buttons.
- Separation via white-card-on-canvas + 1px border, not heavy shadows.
- Font: Inter (imported in the CSS block), weights 400–700.
- Section labels: 11px, uppercase, letter-spacing 0.8px, MUTED.

## Component patterns

- **Stock cards** (`_stock_card()` in dashboard.py): horizontal scroll row;
  circular ACCENT_SOFT logo chip, ticker + company name, sparkline top-right,
  then "Total Share" / "Total Return" label-value rows. Return value colored
  SUCCESS/DANGER with ▲/▼.
- **Sparklines** (`_sparkline()`): SVG polyline + gradient area fill fading
  to transparent (NextAdmin look). Each needs a unique gradient `uid` (use
  the ticker) or the SVG defs collide. Must survive empty/constant series.
- **Screener table**: `st.dataframe` with `ProgressColumn` (AI Score,
  Sentiment, Confidence), `LineChartColumn` (3M trend), emoji badges
  🟢/🟡/🔴 for BUY/HOLD/AVOID.
- **Metric tiles**: `st.metric` styled by the CSS block — uppercase 12px
  label, 28px bold value.
- **Plotly charts**: always through `_theme()` — `plotly_white`, `#F8FAFC`
  plot bg, `#F1F5F9` gridlines, Inter, unified hover. New charts must use it.

## Streamlit-specific hard rules

- EVERY interactive widget needs a unique `key=` or Streamlit throws
  `StreamlitDuplicateElementId`.
- Theme edits in `.streamlit/config.toml` need a server restart.
- Results that must survive tab switches live in `st.session_state`
  (see `sc_df`, `sig_df`, `bt`).
- Money labels are £/nominal (user is UK-based); prices display in $ where
  they come straight from yfinance.
- The OpenAI key auto-loads from `.env` — never add a key input widget.
- Horizontal scroll is allowed ONLY inside the stock-card row
  (`overflow-x:auto` on that flex container), never on the page body.

## Verify visually

Launch `python -m streamlit run dashboard.py --server.port 8501`, open it in
the browser tools, screenshot each affected tab, and LOOK at the screenshots
— especially sidebar contrast and card rendering. Offline Demo mode in the
sidebar gives synthetic data when there's no network.
