"""Market-regime gate: is the broad market rising or falling?

Uses the official TSE equal-weighted index (شاخص هموزن) as the regime anchor:
- equal-weighted reflects the average stock better than cap-weighted شاخص کل,
  which is dominated by a few giants (پالایشی/فلزات).
Rule (conservative default): only allow new buy candidates when the equal-
weighted index closes above its own EMA50. Below it, the gate outputs 'wait'.

This is a market-state input for the decision gate, not a standalone signal.
"""
import pandas as pd

INDEX_NAME = 'شاخص كل'   # pytse uses Arabic ك in the index key


def fetch_equal_weighted_index():
    from pytse_client import download_financial_indexes
    d = download_financial_indexes(symbols=INDEX_NAME, write_to_csv=False)
    df = d[INDEX_NAME] if isinstance(d, dict) else d
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def market_regime(df=None, *, ema_span=50) -> dict:
    """Return regime verdict for the equal-weighted TSE index."""
    if df is None:
        df = fetch_equal_weighted_index()
    close = df['close'].astype(float)
    ema = close.ewm(span=ema_span, adjust=False, min_periods=ema_span).mean()
    last_close, last_ema = float(close.iloc[-1]), float(ema.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close
    return {
        'session': df['date'].iloc[-1].date().isoformat(),
        'last_close': last_close,
        'daily_change_pct': round(100 * (last_close / prev_close - 1), 2),
        'ema50': round(last_ema, 0),
        'regime': 'rising' if last_close > last_ema else 'falling',
        'buy_gate_open': last_close > last_ema,
    }


if __name__ == '__main__':
    import json, sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(market_regime(), ensure_ascii=False, indent=1))
