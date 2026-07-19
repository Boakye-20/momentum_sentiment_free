"""
src/regime.py — optional Hidden-Markov-Model market-regime detection.

Drop-in alternative to `momentum.breadth_regime`: returns the same
risk_on / neutral / risk_off label Series, so signals/backtest code needs
no changes. Enable via `CFG.momentum.regime_method = "hmm"` (CONFIG tab or
config.py). Requires the free `hmmlearn` package; anything missing or
failing falls back to breadth silently upstream.

Deliberate differences from the "7-state HMM" YouTube recipe this came from:
  * 3 states, not 7 — with ~2,800 daily samples a 7-state Gaussian HMM is
    badly overfit (the video trained on 17,000 hourly crypto bars).
  * Walk-forward, not full-sample: the model is refit each year on an
    expanding window of PAST data only, then labels the following year.
    Full-sample fitting looks great in backtests precisely because it has
    seen the future. The first `min_train` days label as "neutral".
  * States are named by their mean market return in the TRAINING window
    (best -> risk_on, worst -> risk_off), never by eyeballing the chart.
  * No leverage — regime output only scales exposure like breadth does.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from config import CFG


def _features(prices: pd.DataFrame) -> pd.DataFrame:
    """Market-level features: equal-weight return, rolling vol, dispersion."""
    rets = prices.pct_change()
    mkt = rets.mean(axis=1)
    return pd.DataFrame({
        "ret":  mkt,
        "vol":  mkt.rolling(21).std(),
        "disp": rets.std(axis=1),          # cross-sectional dispersion
    }).dropna()


def hmm_regime(
    prices: pd.DataFrame,
    n_states: int = 3,
    min_train: int = 756,      # ~3 years before the first prediction
    refit_every: int = 252,    # refit annually on the expanding window
) -> pd.Series:
    """
    Walk-forward Gaussian-HMM regime labels for a wide price frame.
    Raises ImportError if hmmlearn is not installed — the caller
    (momentum.build_panels) catches it and falls back to breadth.
    """
    from hmmlearn.hmm import GaussianHMM  # optional dependency

    feats = _features(prices)
    labels = pd.Series("neutral", index=prices.index, name="regime")
    X = feats.values
    idx = feats.index
    ret = feats["ret"].values

    start = min_train
    while start < len(feats):
        end = min(start + refit_every, len(feats))
        train = X[:start]
        mu, sd = train.mean(axis=0), train.std(axis=0)
        sd[sd == 0] = 1.0
        model = GaussianHMM(
            n_components=n_states, covariance_type="diag",
            n_iter=200, random_state=CFG.backtest.random_seed,
        )
        try:
            model.fit((train - mu) / sd)
            states = model.predict((X[:end] - mu) / sd)
        except Exception as e:
            print(f"[regime] HMM fit failed at {idx[start].date()} ({e}) "
                  f"— labelling block neutral.")
            start = end
            continue

        # Name states by mean training-window market return.
        tr = states[:start]
        mean_ret = {
            s: (ret[:start][tr == s].mean() if (tr == s).any() else 0.0)
            for s in range(n_states)
        }
        order = sorted(mean_ret, key=mean_ret.get)
        name = {order[0]: "risk_off", order[-1]: "risk_on"}
        labels.loc[idx[start:end]] = [
            name.get(s, "neutral") for s in states[start:end]
        ]
        start = end

    counts = labels.value_counts().to_dict()
    print(f"[regime] HMM walk-forward labels: {counts}")
    return labels
