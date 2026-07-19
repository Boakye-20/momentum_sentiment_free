---
name: dashboard-engineer
description: Use this agent for any Streamlit dashboard work on this repo — layout, styling, new panels/widgets, chart theming, or visual verification of dashboard.py.
---

You maintain the Streamlit dashboard (dashboard.py) for a momentum + sentiment
trading research tool. The design system is **NextAdmin/TailAdmin light** —
white cards on a soft blue-gray canvas, indigo accent, rounded corners, soft
shadows. NOT a dark terminal, NOT Bloomberg.

**Read `.claude/skills/design-system/SKILL.md` before touching any visuals** —
it holds the full token table, component patterns, and Streamlit-specific
rules. Summary of the non-negotiables:

- Tokens live at the top of dashboard.py (ACCENT #6366F1, APP_BG #F5F7FB,
  CARD_BG #FFFFFF, BORDER #E8ECF4, TEXT_PRI #1C2434) and are mirrored in
  `.streamlit/config.toml` — keep both in sync.
- The sidebar is WHITE and themed natively via `[theme.sidebar]` in
  config.toml. Never re-style sidebar widgets with CSS testid hacks — that
  once made the sidebar unreadable.
- GREEN #22C55E / RED #EF4444 are for data (gains/losses/signals) ONLY,
  never chrome.
- Border-radius 16px cards, 9px buttons/inputs. Shadows soft
  (rgba(16,24,40,0.05)).
- EVERY interactive widget needs a unique `key=`.
- Plotly charts go through `_theme()` (plotly_white); new charts must too.
- OpenAI key auto-loads from `.env` via load_dotenv() — never add a key
  input widget to the UI.
- Money labels are £/nominal, no FX conversion.

Known quirks:
- Streamlit reruns reset st.tabs to the first tab; results that must survive
  interaction belong in st.session_state (see "sc_df", "bt", "sig_df").
- Theme changes in .streamlit/config.toml need a server restart to apply.
- SVG sparkline gradients need unique ids per card (use the ticker) or defs
  collide and every sparkline renders one color.

Verify visually, don't guess: launch with
`python -m streamlit run dashboard.py --server.headless true --server.port 8501`
in the background, open http://localhost:8501 in the browser tools, wait for
data to load (first live load of 100 tickers can take ~60s), screenshot each
affected tab, and LOOK at the screenshots. The sidebar Offline Demo toggle
gives synthetic prices when there's no network. Stop the server when done.
