"""Synthetic regime-gate tests; not market evidence."""
import importlib.util
import unittest
from pathlib import Path

import pandas as pd


def load():
    p = Path(__file__).with_name('regime_gate.py')
    assert p.exists(), 'Missing regime_gate.py'
    spec = importlib.util.spec_from_file_location('regime_gate', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def index_df(closes):
    n = len(closes)
    dates = pd.bdate_range('2025-01-01', periods=n)
    return pd.DataFrame({'date': dates, 'close': closes,
                         'open': closes, 'high': closes, 'low': closes,
                         'volume': [1] * n})


class RegimeTests(unittest.TestCase):
    def test_rising_market_gate_open(self):
        m = load()
        df = index_df([100 + i for i in range(120)])
        out = m.market_regime(df)
        self.assertEqual(out['regime'], 'rising')
        self.assertTrue(out['buy_gate_open'])

    def test_falling_market_gate_closed(self):
        m = load()
        df = index_df([300 - i for i in range(120)])
        out = m.market_regime(df)
        self.assertEqual(out['regime'], 'falling')
        self.assertFalse(out['buy_gate_open'])

    def test_session_is_index_date_not_today(self):
        m = load()
        df = index_df([100 + i for i in range(120)])
        out = m.market_regime(df)
        self.assertEqual(out['session'], df['date'].iloc[-1].date().isoformat())

    def test_daily_change_sign_matches_direction(self):
        m = load()
        closes = [100] * 60 + [100 + i for i in range(60)]
        out = m.market_regime(index_df(closes))
        self.assertGreater(out['daily_change_pct'], 0)


if __name__ == '__main__':
    unittest.main()
