"""Exploratory technical-only research; never a production strategy validation.

Fixed rule: close > EMA20 > EMA50 and 50 <= Wilder RSI14 <= 65.
Indicator warmup is causal. Corporate-action data may not be point-in-time.
"""
from __future__ import annotations

import math

import pandas as pd


def performance(equity, *, initial=1.0) -> dict:
    """Simple cumulative return and signed peak-to-trough drawdown (no annualizing)."""
    values = [float(initial)] + [float(x) for x in equity]
    if initial <= 0 or any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError("equity must be finite and positive")
    peak, drawdown = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return {"total_return": values[-1] / initial - 1, "max_drawdown": drawdown}


def indicators(close: pd.Series) -> pd.DataFrame:
    """EMA20/50 and SMA-seeded Wilder RSI14, using completed bars only."""
    close = close.astype(float)
    delta = close.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    rsi = pd.Series(float("nan"), index=close.index)
    if len(close) > 14:
        gain, loss = gains.iloc[1:15].mean(), losses.iloc[1:15].mean()
        for i in range(14, len(close)):
            if i > 14:
                gain = (gain * 13 + gains.iloc[i]) / 14
                loss = (loss * 13 + losses.iloc[i]) / 14
            rsi.iloc[i] = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
    result = pd.DataFrame({
        "ema20": close.ewm(span=20, adjust=False, min_periods=20).mean(),
        "ema50": close.ewm(span=50, adjust=False, min_periods=50).mean(),
        "rsi14": rsi,
    })
    result["signal"] = (close > result.ema20) & (result.ema20 > result.ema50) & result.rsi14.between(50, 65)
    return result


def run_backtest(bars: pd.DataFrame, *, completed_through,
                 price_basis: str, fill_policy="hypothetical_next_open",
                 buy_fee=0.0037, sell_fee=0.0088, slippage=0.002) -> dict:
    """Run the fixed technical proxy on the latest available calendar year.

    bars: ascending, unique date/open/high/low/close/volume on a single adjusted
    basis; close means last trade, not weighted daily final. completed_through
    is a caller-supplied completed-session cutoff, not download time.
    Fees are assumptions, not verified exchange tariffs. Fractional adjusted
    units, 100% notional long/cash, no leverage. All results are normalized.
    No tuning, fundamentals, Codal, investor flow or market-universe backtest.
    """
    required = {"date", "open", "high", "low", "close", "volume"}
    if not isinstance(bars, pd.DataFrame) or not required.issubset(bars.columns):
        raise ValueError("require date/open/high/low/close/volume columns")
    if price_basis != "provider_adjusted_ohlc":
        raise ValueError("explicit provider_adjusted_ohlc basis required; raw prices forbidden")
    if fill_policy != "hypothetical_next_open":
        raise ValueError("only hypothetical_next_open is currently supported")
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x < 1
           for x in (buy_fee, sell_fee, slippage)):
        raise ValueError("cost assumptions must be finite rates in [0, 1)")
    data = bars.copy()
    data["date"] = pd.to_datetime(data.date, errors="raise")
    through = pd.Timestamp(completed_through)
    if pd.isna(through) or through.tzinfo is not None or data.date.dt.tz is not None:
        raise ValueError("use timezone-naive completed session dates")
    if data.date.isna().any() or not data.date.is_monotonic_increasing or data.date.duplicated().any():
        raise ValueError("session dates must be unique and ascending")
    data = data[data.date <= through].reset_index(drop=True)
    if data.empty:
        raise ValueError("no completed bars")
    for column in ("open", "high", "low", "close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="raise").astype(float)
        if not data[column].map(lambda x: math.isfinite(x) and x > 0).all():
            raise ValueError("prices and traded volume must be finite and positive")
    if ((data.low > data[["open", "close"]].min(axis=1)) |
            (data.high < data[["open", "close"]].max(axis=1))).any():
        raise ValueError("invalid OHLC bounds")
    cutoff = data.date.iloc[-1] - pd.DateOffset(years=1)
    first = int(data.index[data.date > cutoff][0])
    if first < 150:
        raise ValueError("need at least 150 earlier observed bars before latest-year holdout")
    signals = indicators(data.close).signal
    cash, units, entry_i = 1.0, 0.0, None
    trades, curve = [], []
    benchmark_units = 1 / (float(data.open.iloc[first]) * (1 + slippage) * (1 + buy_fee))
    for i in range(first, len(data)):
        day = data.date.iloc[i].date().isoformat()
        prior_signal = bool(signals.iloc[i - 1])
        exited = False
        if units and (not prior_signal or i - entry_i >= 20):
            fill = float(data.open.iloc[i]) * (1 - slippage)
            cash = units * fill * (1 - sell_fee)
            trades[-1].update(exit_index=i, exit_date=day, exit_fill=fill,
                              exit_signal_date=data.date.iloc[i - 1].date().isoformat(),
                              exit_reason="max_holding" if i - entry_i >= 20 else "signal_loss",
                              holding_sessions=i - entry_i,
                              net_return=cash / trades[-1]["entry_equity"] - 1)
            units, entry_i, exited = 0.0, None, True
        if not units and not exited and prior_signal:
            fill = float(data.open.iloc[i]) * (1 + slippage)
            units = cash / (fill * (1 + buy_fee))
            entry_i = i
            trades.append({"signal_date": data.date.iloc[i - 1].date().isoformat(),
                           "entry_index": i, "entry_date": day, "entry_fill": fill,
                           "entry_equity": cash, "exit_index": None, "exit_date": None,
                           "net_return": None})
            cash = 0.0
        curve.append({"date": day, "equity": cash + units * float(data.close.iloc[i]),
                      "benchmark_equity": benchmark_units * float(data.close.iloc[i])})
    metrics = performance([r["equity"] for r in curve])
    metrics.update(entries=len(trades), closed_trades=sum(t["exit_index"] is not None for t in trades),
                   open_positions=int(units > 0))
    gaps = data.date.diff().dt.days
    large_gaps = [{"from": data.date.iloc[i - 1].date().isoformat(),
                   "to": data.date.iloc[i].date().isoformat(), "calendar_days": int(gaps.iloc[i])}
                  for i in data.index[gaps > 10]]
    return {
        "data_quality": {"exchange_calendar_verified": False,
                         "max_calendar_gap_days": int(gaps.max()),
                         "gaps_over_10_calendar_days": large_gaps,
                         "warning": "UNEXPLAINED gaps: missing records versus halts/closures unresolved; metrics are illustrative only."
                                    if large_gaps else "Calendar completeness unverified even when no long gap is detected."},
        "status": "exploratory_unvalidated", "production_validated": False,
        "scope": "Fixed technical proxy only; NOT full Codal/flow strategy backtest",
        "rule": "close > EMA20 > EMA50 and 50 <= Wilder RSI14 <= 65; next-open exit on signal loss or after 20 observed sessions",
        "holdout": {"start": data.date.iloc[first].date().isoformat(),
                    "end": data.date.iloc[-1].date().isoformat(),
                    "sessions": len(curve), "warmup_sessions": first,
                    "selection": "latest available calendar year, no tuning; not prospective validation"},
        "assumptions": {"price_basis": price_basis, "fill_policy": fill_policy,
                        "buy_fee": buy_fee, "sell_fee": sell_fee, "slippage_per_side": slippage,
                        "max_holding_sessions": 20, "terminal_mark": "close mark, no forced terminal fill or sale cost",
                        "position": "fractional adjusted units, all notional capital, long/cash"},
        "caveats": [
            "Daily limits, queues, halts and executable open liquidity unavailable: fills are hypothetical, not validated.",
            "Corporate-action ledger and point-in-time adjustments unavailable: adjusted data are a provider proxy, not verified total return.",
            "20 sessions means observed bars, not guaranteed exchange sessions or calendar days; missing sessions/halt delays unmodeled.",
            "Single selected surviving symbol has selection/survivorship bias; no market benchmark, only same-symbol buy-and-hold.",
            "Fees/slippage are explicit assumptions; no capacity, lot-size or dividend/rights cash ledger.",
            "Latest historical year is not a prospective untouched holdout; no profitability or production claims.",
        ],
        "metrics": metrics,
        "benchmark": {**performance([r["benchmark_equity"] for r in curve]),
                      "name": "same_symbol_buy_and_hold", "entry": "first holdout open, same buy costs; terminal close mark without sale"},
        "trades": trades, "equity_curve": curve,
    }
