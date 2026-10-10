"""Synthetic tests, never evidence of market performance."""
import importlib.util
import unittest

import pandas as pd


def fixture():
    import numpy as np
    x = np.arange(650)
    close = 100 + x * .06 + 2 * np.sin(x / 4)
    return pd.DataFrame({"date": pd.bdate_range("2022-01-01", periods=len(x)),
                         "open": close * 1.001, "high": close * 1.02,
                         "low": close * .98, "close": close, "volume": 1000})


class BacktestTests(unittest.TestCase):
    def test_holdout_next_open_and_costs(self):
        import backtest_core as core
        self.assertTrue(hasattr(core, "run_backtest"), "missing simulator")
        data = fixture()
        result = core.run_backtest(data, completed_through=data.date.iloc[-1],
                                   price_basis="provider_adjusted_ohlc",
                                   fill_policy="hypothetical_next_open")
        self.assertEqual(result["status"], "exploratory_unvalidated")
        self.assertFalse(result["production_validated"])
        self.assertGreater(len(result["trades"]), 1)
        signal = core.indicators(data.close).signal
        cutoff = data.date.iloc[-1] - pd.DateOffset(years=1)
        first = data.index[data.date > cutoff][0]
        self.assertEqual(result["holdout"]["start"], data.date.iloc[first].date().isoformat())
        for trade in result["trades"]:
            entry = trade["entry_index"]
            self.assertGreaterEqual(entry, first)
            self.assertTrue(signal.iloc[entry - 1])
            self.assertEqual(trade["signal_date"], data.date.iloc[entry - 1].date().isoformat())
            self.assertAlmostEqual(trade["entry_fill"], data.open.iloc[entry] * 1.002)
            if trade["exit_index"] is not None:
                exit_i = trade["exit_index"]
                self.assertLessEqual(exit_i - entry, 20)
                self.assertTrue(not signal.iloc[exit_i - 1] or exit_i - entry == 20)
                expected = (data.open.iloc[exit_i] * .998 * .9912) / (data.open.iloc[entry] * 1.002 * 1.0037) - 1
                self.assertAlmostEqual(trade["net_return"], expected)
        expected_benchmark = data.close.iloc[-1] / (data.open.iloc[first] * 1.002 * 1.0037) - 1
        self.assertAlmostEqual(result["benchmark"]["total_return"], expected_benchmark)
        self.assertAlmostEqual(result["metrics"]["max_drawdown"], core.performance([r["equity"] for r in result["equity_curve"]])["max_drawdown"])

    def test_invalid_or_unadjusted_inputs_fail_closed(self):
        import backtest_core as core
        data = fixture()
        cases = [(data, {"price_basis": "raw"}),
                 (data, {"buy_fee": -.1}),
                 (data, {"slippage": float("nan")}),
                 (data, {"fill_policy": "guaranteed"}),
                 (data.iloc[-300:], {}),
                 (data.iloc[::-1], {}),
                 (pd.concat([data, data.iloc[-1:]]), {}),
                 (data.assign(open=0), {}),
                 (data.assign(high=data.low), {}),
                 (data.assign(volume=-1), {}),
                 (data.assign(close=float("inf")), {}),
                 (data.drop(columns="volume"), {}),
                 (data.iloc[:0], {})]
        for frame, extra in cases:
            options = {"completed_through": data.date.iloc[-1], "price_basis": "provider_adjusted_ohlc", **extra}
            with self.subTest(options=extra, rows=len(frame)):
                with self.assertRaises(ValueError):
                    core.run_backtest(frame, **options)

    def test_mutating_future_does_not_change_past_fills(self):
        from backtest_core import run_backtest
        data = fixture()
        options = {"completed_through": data.date.iloc[-1], "price_basis": "provider_adjusted_ohlc"}
        original = run_backtest(data, **options)
        boundary = original["trades"][2]["entry_index"]
        changed = data.copy()
        changed.loc[boundary:, ["open", "high", "low", "close"]] *= 1.5
        changed.loc[boundary, "open"] = data.open.iloc[boundary]
        changed.loc[boundary, "low"] = data.low.iloc[boundary]
        altered = run_backtest(changed, **options)
        self.assertEqual(original["equity_curve"][:boundary - original["holdout"]["warmup_sessions"]],
                         altered["equity_curve"][:boundary - original["holdout"]["warmup_sessions"]])
        for key in ("entry_date", "entry_fill", "signal_date"):
            self.assertEqual(original["trades"][2][key], altered["trades"][2][key])
        # Future rows beyond an explicitly completed session cannot affect even holdout selection.
        through = data.date.iloc[-20]
        self.assertEqual(run_backtest(data, completed_through=through, price_basis="provider_adjusted_ohlc"),
                         run_backtest(data.iloc[:-19], completed_through=through, price_basis="provider_adjusted_ohlc"))

    def test_twenty_session_exit_and_no_forced_terminal_fill(self):
        import numpy as np
        from backtest_core import run_backtest
        data = fixture()
        x = np.arange(len(data))
        data["close"] = 100 + x * .04 + .2 * (x % 2)
        data["open"], data["high"], data["low"] = data.close, data.close + 1, data.close - 1
        result = run_backtest(data, completed_through=data.date.iloc[-1], price_basis="provider_adjusted_ohlc")
        closed = [t for t in result["trades"] if t["exit_index"] is not None]
        self.assertGreater(len(closed), 1)
        self.assertTrue(all(t["exit_reason"] == "max_holding" and t["holding_sessions"] == 20 for t in closed))
        self.assertIsNone(result["trades"][-1]["exit_index"])
        self.assertEqual(result["metrics"]["open_positions"], 1)

    def test_rsi_wilder_seed_and_flat_series(self):
        from backtest_core import indicators
        close = pd.Series([100 + i % 2 for i in range(20)])
        rsi = indicators(close).rsi14
        self.assertAlmostEqual(rsi.iloc[14], 50)
        self.assertAlmostEqual(rsi.iloc[15], 100 - 100 / (1 + ((.5 * 13 + 1) / 14) / ((.5 * 13) / 14)))
        self.assertTrue((indicators(pd.Series([100] * 60)).rsi14.dropna() == 50).all())

    def test_unexplained_calendar_gaps_are_prominent(self):
        from backtest_core import run_backtest
        data = fixture().drop(index=range(470, 510)).reset_index(drop=True)
        result = run_backtest(data, completed_through=data.date.iloc[-1], price_basis="provider_adjusted_ohlc")
        self.assertIn("data_quality", result)
        self.assertFalse(result["data_quality"]["exchange_calendar_verified"])
        self.assertGreater(result["data_quality"]["max_calendar_gap_days"], 30)
        self.assertEqual(len(result["data_quality"]["gaps_over_10_calendar_days"]), 1)
        self.assertIn("UNEXPLAINED", result["data_quality"]["warning"])

    def test_fixed_indicators_are_causal(self):
        self.assertIsNotNone(importlib.util.find_spec("backtest_core"), "missing backtest implementation")
        from backtest_core import indicators
        close = pd.Series([100 + i * .2 + (i % 4) * .3 for i in range(100)])
        full = indicators(close)
        prefix = indicators(close.iloc[:80])
        pd.testing.assert_frame_equal(full.iloc[:80], prefix)
        self.assertTrue(full.ema50.iloc[:49].isna().all())
        self.assertFalse(full.signal.iloc[:49].any())
        self.assertAlmostEqual(full.ema20.iloc[-1], close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1])
        self.assertEqual(list(full.columns), ["ema20", "ema50", "rsi14", "signal"])
        self.assertTrue(((full.rsi14.dropna() >= 0) & (full.rsi14.dropna() <= 100)).all())

    def test_drawdown_includes_initial_capital(self):
        import backtest_core as core
        self.assertTrue(hasattr(core, "performance"), "missing metrics")
        stats = core.performance([.9, 1.2, .6, .8], initial=1)
        self.assertAlmostEqual(stats["total_return"], -.2)
        self.assertAlmostEqual(stats["max_drawdown"], -.5)
        self.assertAlmostEqual(core.performance([.9], initial=1)["max_drawdown"], -.1)


if __name__ == "__main__":
    unittest.main()
