"""
scripts/portfolio_alerts.py — email alert when a held stock drops off the
Signal Book (i.e. the model would no longer buy it, but this is a long-only
app with no sell button, so nothing acts on that automatically).

Reuses api/server.py's own T212 fetch + signal-weight logic directly (no
FastAPI process needs to be running) so this always agrees with what the
Portfolio page shows — one signal system, not two.

Called from scripts/daily_fetch.py after the price cache refresh. Best-effort:
skipped silently if T212 or SMTP env vars aren't configured, same as the other
optional steps in daily_fetch.py.
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _t212_creds() -> tuple[str, str, str] | None:
    key = os.environ.get("T212_API_KEY", "").strip()
    secret = os.environ.get("T212_API_SECRET", "").strip()
    if not key or key.startswith("your_") or secret.startswith("your_"):
        return None
    env = os.environ.get("T212_ENV", "live").strip().lower()
    host = "demo" if env == "demo" else "live"
    import base64
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return host, f"Basic {token}", env


def find_dropped_positions() -> tuple[list[dict], str]:
    """Returns (dropped_positions, env_label). Each dropped position dict has
    ticker/quantity/market_value. Empty list if none dropped or T212 isn't
    configured."""
    creds = _t212_creds()
    if creds is None:
        return [], ""
    host, auth, env = creds

    from api import server as srv  # loads .env, gives us the exact same logic
    import pandas as pd

    positions = srv._fetch_t212_positions(host, auth)
    df, _as_of = srv._screener_df()
    w_now = srv._signal_weights_at(str(pd.Timestamp.today().normalize().date()))

    dropped = []
    for p in positions:
        raw = p.get("instrument", {}).get("ticker", "")
        sym = raw.split("_")[0]
        if sym not in df.index:
            continue  # not in universe at all — not a signal-drop, a different case
        still_signaled = sym in w_now.index and w_now[sym] > 0
        if not still_signaled:
            wallet = p.get("walletImpact", {})
            dropped.append({
                "ticker": sym,
                "quantity": p.get("quantity"),
                "market_value": wallet.get("currentValue"),
            })
    return dropped, env


def _send_email(dropped: list[dict], env: str) -> None:
    user = os.environ.get("GMAIL_USER", "").strip()
    app_pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to = os.environ.get("ALERT_EMAIL_TO", "").strip() or user
    if not user or not app_pw:
        print("[portfolio_alerts] GMAIL_USER/GMAIL_APP_PASSWORD not set — skipping email.")
        return

    lines = [f"{p['ticker']}: {p['quantity']} shares, "
             f"£{p['market_value']:.2f}" if isinstance(p.get('market_value'), (int, float))
             else f"{p['ticker']}: {p['quantity']} shares"
             for p in dropped]
    plural = "s" if len(dropped) != 1 else ""
    body = (
        f"Signal Book Alert ({env.upper()} account)\n\n"
        f"The following holding{plural} no longer qualif{'y' if plural else 'ies'} "
        f"for a buy signal:\n\n"
        + "\n".join(f"  - {l}" for l in lines)
        + "\n\n"
        "This tool is long-only and does not place sell orders. "
        "Review these positions in the Portfolio page and decide manually "
        "whether to sell in Trading212.\n\n"
        "Not investment advice."
    )

    msg = EmailMessage()
    msg["Subject"] = f"Signal Book Alert: {len(dropped)} holding{plural} no longer signaled"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(user, app_pw)
        smtp.send_message(msg)
    print(f"[portfolio_alerts] alert email sent to {to} ({len(dropped)} dropped).")


def main() -> int:
    dropped, env = find_dropped_positions()
    if not dropped:
        print("[portfolio_alerts] no dropped positions (or T212 not configured).")
        return 0
    print(f"[portfolio_alerts] {len(dropped)} position(s) dropped off the Signal Book: "
          + ", ".join(p["ticker"] for p in dropped))
    _send_email(dropped, env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
