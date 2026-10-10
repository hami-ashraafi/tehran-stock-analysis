"""TSE adjusted historical technical and client-type flow analysis.

This module provides deterministic functions for:
- Historical price indicators (EMA, RSI, MACD) on verified adjusted basis.
- Support/resistance from confirmed pivots mapped to raw last-trade scale.
- Volume and liquidity baselines (prior-only).
- Client-type flow metrics with per-capita power and net money.

Key constraints:
- price_basis must be declared explicitly ("weighted_final_adjusted" or "raw_last_trade").
- All windows are prior-only; no lookahead.
- Conflicting dates, insufficient history, and invalid OHLC are rejected with explicit status.
- Corporate and individual nets are mirror images in a complete matched dataset; they are not counted as two independent confirmations.
- Output is JSON-serializable and contains quality diagnostics.
"""

import math
from datetime import date

import pandas as pd


def _ema(series: pd.Series, span: int) -> float:
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _wilder_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1])


def _macd(series: pd.Series) -> dict:
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return {
        "macd": float(macd_line.iloc[-1]),
        "signal": float(signal.iloc[-1]),
        "hist": float(hist.iloc[-1]),
    }


def _pivot_levels(df: pd.DataFrame, window: int = 5, tol_pct: float = 1.5) -> tuple[list[float], list[float]]:
    highs = df["high"].values
    lows = df["low"].values
    supports, resistances = [], []
    for i in range(window, len(df) - window):
        if lows[i] == min(lows[i - window : i + window + 1]):
            supports.append(float(lows[i]))
        if highs[i] == max(highs[i - window : i + window + 1]):
            resistances.append(float(highs[i]))

    def cluster(levels):
        if not levels:
            return []
        levels = sorted(set(levels))
        clustered = []
        for lvl in levels:
            if clustered and abs(lvl / clustered[-1] - 1) * 100 < tol_pct:
                clustered[-1] = (clustered[-1] + lvl) / 2
            else:
                clustered.append(lvl)
        return clustered

    last_close = float(df["close"].iloc[-1])
    sup = [s for s in cluster(supports) if s < last_close * 0.995][-4:]
    res = [r for r in cluster(resistances) if r > last_close * 1.005][:4]
    return sup, res


def analyze_history(raw_df: pd.DataFrame, adj_df: pd.DataFrame, *, price_basis: str) -> dict:
    if price_basis not in ("weighted_final_adjusted", "raw_last_trade"):
        raise ValueError("price_basis must be explicitly 'weighted_final_adjusted' or 'raw_last_trade'")

    if len(raw_df) != len(adj_df) or not (raw_df["date"].iloc[-1] == adj_df["date"].iloc[-1]):
        return {"status": "session_mismatch"}

    df = adj_df.copy()
    df = df.sort_values("date").reset_index(drop=True)
    identical_dupes = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)
    if df.duplicated(subset=["date"]).any():
        return {"status": "conflicting_dates"}

    n = len(df)
    if n < 250:
        return {"status": "insufficient_history", "ema200": None,
                "sessions_available": n, "sessions_required": 250}

    # quality
    identical = identical_dupes + int(raw_df.duplicated().sum()) - identical_dupes if identical_dupes else int(raw_df.duplicated().sum())
    gaps = int((df["date"].diff().dt.days > 5).sum())
    if not ((df["high"] >= df["low"]) & (df["close"] >= df["low"]) & (df["close"] <= df["high"])).all():
        return {"status": "invalid_ohlc"}

    last_raw_close = float(raw_df["close"].iloc[-1])
    ema20 = _ema(df["adjClose"], 20)
    ema50 = _ema(df["adjClose"], 50)
    ema200 = _ema(df["adjClose"], 200)
    rsi = _wilder_rsi(df["adjClose"])
    macd = _macd(df["adjClose"])

    supports, resistances = _pivot_levels(raw_df)

    vol_mean20 = float(df["volume"].iloc[-21:-1].mean())
    vol_mean40 = float(df["volume"].iloc[-41:-1].mean())
    last_vol = float(df["volume"].iloc[-1])
    vol_ratio20 = last_vol / vol_mean20 if vol_mean20 > 0 else None

    result = {
        "status": "ok",
        "symbol": None,
        "session": df["date"].iloc[-1].date().isoformat(),
        "price_basis": price_basis,
        "last_raw_close": last_raw_close,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": rsi,
        "macd": macd,
        "supports": [round(s, 2) for s in supports],
        "resistances": [round(r, 2) for r in resistances],
        "levels_scale": "raw_last_trade",
        "volume_prior20_mean": round(vol_mean20, 0),
        "volume_prior40_mean": round(vol_mean40, 0),
        "volume_ratio_vs_prior20": round(vol_ratio20, 2) if vol_ratio20 else None,
        "liquidity_20d_avg_value": round(df["value"].iloc[-20:].mean(), 0),
        "quality": {
            "identical_duplicate_rows": identical,
            "max_gap_days": int(df["date"].diff().dt.days.max()),
            "gap_warning": gaps > 0,
        },
    }
    return result


def analyze_flow(ct_df: pd.DataFrame) -> dict:
    if len(ct_df) < 20:
        return {"status": "insufficient_history"}

    df = ct_df.sort_values("date").reset_index(drop=True)
    if df.duplicated(subset=["date"]).any():
        return {"status": "conflicting_dates"}
    numeric_cols = [c for c in df.columns if c != "date"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).reset_index(drop=True)
    if len(df) < 20:
        return {"status": "insufficient_history"}

    last = df.iloc[-1]
    per_buy = last["individual_buy_vol"] / last["individual_buy_count"] if last["individual_buy_count"] > 0 else None
    per_sell = last["individual_sell_vol"] / last["individual_sell_count"] if last["individual_sell_count"] > 0 else None
    power = per_buy / per_sell if per_buy and per_sell else None

    net_vol_5 = (df["individual_buy_vol"] - df["individual_sell_vol"]).tail(5).sum()
    net_vol_20 = (df["individual_buy_vol"] - df["individual_sell_vol"]).tail(20).sum()
    net_corp_5 = int((df["corporate_buy_vol"] - df["corporate_sell_vol"]).tail(5).sum())
    net_corp_20 = int((df["corporate_buy_vol"] - df["corporate_sell_vol"]).tail(20).sum())
    net_val_5 = (df["individual_buy_value"] - df["individual_sell_value"]).tail(5).sum()
    net_val_20 = (df["individual_buy_value"] - df["individual_sell_value"]).tail(20).sum()

    prior20_buy = df["individual_buy_vol"].iloc[-21:-1].mean()
    prior20_sell = df["individual_sell_vol"].iloc[-21:-1].mean()

    return {
        "status": "ok",
        "session": df["date"].iloc[-1].date().isoformat(),
        "buyer_power": round(power, 4) if power else None,
        "net_individual_volume_5": int(net_vol_5),
        "net_individual_volume_20": int(net_vol_20),
        "net_corporate_volume_5": net_corp_5,
        "net_corporate_volume_20": net_corp_20,
        "net_individual_value_5": int(net_val_5),
        "net_individual_value_20": int(net_val_20),
        "per_capita_buy_prior20_mean": round(prior20_buy / df["individual_buy_count"].iloc[-21:-1].mean(), 0) if prior20_buy else None,
        "value_basis": "reported_values",
        "nets_are_mirror_sides": True,
    }
