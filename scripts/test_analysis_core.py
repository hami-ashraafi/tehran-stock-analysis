"""Synthetic analysis tests. Fixtures are constructed, not market evidence."""
import importlib.util
import math
import unittest
from pathlib import Path

import pandas as pd


def load():
    p = Path(__file__).with_name('analysis_core.py')
    assert p.exists(), 'Missing analysis_core.py'
    spec = importlib.util.spec_from_file_location('analysis_core', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def bars(n=320, start='2025-01-01', step=1.0, base=1000.0):
    dates = pd.bdate_range(start, periods=n)
    close = [base + i * step for i in range(n)]
    return pd.DataFrame({'date': dates, 'open': close, 'high': [c * 1.01 for c in close],
                         'low': [c * 0.99 for c in close], 'close': close,
                         'adjClose': close, 'yesterday': [base] + close[:-1],
                         'volume': [1_000_000] * n, 'value': [c * 1_000_000 for c in close],
                         'count': [500] * n})


def flows(n=60, start='2025-06-02'):
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame({'date': dates,
                         'individual_buy_vol': [1_000_000] * n,
                         'individual_sell_vol': [800_000] * n,
                         'corporate_buy_vol': [200_000] * n,
                         'corporate_sell_vol': [400_000] * n,
                         'individual_buy_value': [2_000_000_000] * n,
                         'individual_sell_value': [1_600_000_000] * n,
                         'individual_buy_count': [100] * n,
                         'individual_sell_count': [200] * n})


class HistoryTests(unittest.TestCase):
    def test_indicator_values_match_reference_formulas(self):
        m = load()
        df = bars()
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'ok')
        series = df['adjClose']
        self.assertAlmostEqual(out['ema20'], series.ewm(span=20, adjust=False).mean().iloc[-1], places=6)
        self.assertAlmostEqual(out['ema200'], series.ewm(span=200, adjust=False).mean().iloc[-1], places=6)
        self.assertGreater(out['rsi14'], 90.0)  # monotone rise -> RSI near 100
        self.assertEqual(out['session'], df['date'].iloc[-1].date().isoformat())
        self.assertEqual(out['price_basis'], 'weighted_final_adjusted')

    def test_price_basis_must_be_declared(self):
        m = load()
        df = bars()
        with self.assertRaises(ValueError):
            m.analyze_history(df, df, price_basis='adjClose_means_adjusted')

    def test_insufficient_warmup_is_rejected_not_approximated(self):
        m = load()
        df = bars(n=120)
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'insufficient_history')
        self.assertIsNone(out['ema200'])

    def test_conflicting_duplicate_dates_are_rejected(self):
        m = load()
        df = bars()
        dup = pd.concat([df, df.tail(1).assign(close=9999.0)], ignore_index=True)
        out = m.analyze_history(dup, dup, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'conflicting_dates')

    def test_identical_duplicate_rows_are_collapsed_and_counted(self):
        m = load()
        df = bars()
        dup = pd.concat([df, df.tail(1)], ignore_index=True)
        out = m.analyze_history(dup, dup, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['quality']['identical_duplicate_rows'], 1)

    def test_invalid_ohlc_rows_block_instead_of_being_dropped(self):
        m = load()
        df = bars()
        # make a truly invalid bar: high < low
        idx = df.index[-5]
        df.loc[idx, 'high'] = df.loc[idx, 'low'] - 10
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'invalid_ohlc')

    def test_unexplained_calendar_gap_is_reported(self):
        m = load()
        df = bars()
        df.loc[df.index[-1], 'date'] = df['date'].iloc[-1] + pd.Timedelta(days=200)
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertGreater(out['quality']['max_gap_days'], 100)
        self.assertTrue(out['quality']['gap_warning'])

    def test_volume_baselines_exclude_the_scored_session(self):
        m = load()
        df = bars()
        df.loc[df.index[-1], 'volume'] = 50_000_000
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertAlmostEqual(out['volume_prior20_mean'], 1_000_000.0, places=6)
        self.assertAlmostEqual(out['volume_ratio_vs_prior20'], 50.0, places=6)

    def test_levels_come_from_confirmed_pivots_on_raw_scale(self):
        m = load()
        n = 320
        dates = pd.bdate_range('2025-01-01', periods=n)
        close = [1000 + (50 if i % 40 == 0 else 0) - (40 if i % 37 == 0 else 0) for i in range(n)]
        df = pd.DataFrame({'date': dates, 'open': close, 'high': [c + 5 for c in close],
                           'low': [c - 5 for c in close], 'close': close, 'adjClose': close,
                           'yesterday': [1000] + close[:-1], 'volume': [1_000_000] * n,
                           'value': [c * 1_000_000 for c in close], 'count': [500] * n})
        out = m.analyze_history(df, df, price_basis='weighted_final_adjusted')
        self.assertTrue(all(s < out['last_raw_close'] for s in out['supports']))
        self.assertTrue(all(r > out['last_raw_close'] for r in out['resistances']))
        self.assertEqual(out['levels_scale'], 'raw_last_trade')

    def test_raw_and_adjusted_session_mismatch_blocks(self):
        m = load()
        raw, adj = bars(), bars()
        adj.loc[adj.index[-1], 'date'] = adj['date'].iloc[-1] + pd.Timedelta(days=1)
        out = m.analyze_history(raw, adj, price_basis='weighted_final_adjusted')
        self.assertEqual(out['status'], 'session_mismatch')


class FlowTests(unittest.TestCase):
    def test_buyer_power_uses_volume_per_participant(self):
        m = load()
        out = m.analyze_flow(flows())
        self.assertEqual(out['status'], 'ok')
        self.assertAlmostEqual(out['buyer_power'], (1_000_000 / 100) / (800_000 / 200), places=9)

    def test_money_flow_uses_values_not_volume_times_price(self):
        m = load()
        out = m.analyze_flow(flows())
        self.assertAlmostEqual(out['net_individual_value_5'], 5 * 400_000_000.0, places=6)
        self.assertAlmostEqual(out['net_individual_value_20'], 20 * 400_000_000.0, places=6)
        self.assertEqual(out['value_basis'], 'reported_values')

    def test_zero_participants_yield_missing_metric_not_clipped_denominator(self):
        m = load()
        df = flows()
        df.loc[df.index[-1], 'individual_sell_count'] = 0
        out = m.analyze_flow(df)
        self.assertIsNone(out['buyer_power'])
        self.assertEqual(out['status'], 'ok')

    def test_baselines_are_prior_only(self):
        m = load()
        df = flows()
        df.loc[df.index[-1], 'individual_buy_vol'] = 40_000_000
        out = m.analyze_flow(df)
        self.assertAlmostEqual(out['per_capita_buy_prior20_mean'], 10_000.0, places=6)

    def test_unsorted_input_is_sorted_before_windows(self):
        m = load()
        df = flows().iloc[::-1].reset_index(drop=True)
        out = m.analyze_flow(df)
        self.assertEqual(out['session'], flows()['date'].iloc[-1].date().isoformat())

    def test_conflicting_duplicate_flow_dates_rejected(self):
        m = load()
        df = flows()
        dup = pd.concat([df, df.tail(1).assign(individual_buy_vol=7)], ignore_index=True)
        self.assertEqual(m.analyze_flow(dup)['status'], 'conflicting_dates')

    def test_short_history_is_insufficient(self):
        m = load()
        self.assertEqual(m.analyze_flow(flows(n=10))['status'], 'insufficient_history')

    def test_corporate_and_individual_nets_are_not_two_confirmations(self):
        m = load()
        out = m.analyze_flow(flows())
        self.assertAlmostEqual(out['net_individual_volume_5'] + out['net_corporate_volume_5'], 0.0, places=6)
        self.assertTrue(out['nets_are_mirror_sides'])


if __name__ == '__main__':
    unittest.main()
