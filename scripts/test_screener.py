"""Synthetic unit fixtures only; not market evidence."""
import importlib.util
from pathlib import Path
import unittest

class ScreenerTests(unittest.TestCase):
    def test_net_reward_risk(self):
        path = Path(__file__).with_name('screener.py')
        self.assertTrue(path.exists(), 'Missing screening helper')
        spec = importlib.util.spec_from_file_location('screener', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertAlmostEqual(module.reward_risk(100, 90, 125, 0), 2.5)
        self.assertAlmostEqual(module.reward_risk(100, 90, 125, 2), 23/12)
        self.assertIsNone(module.reward_risk(100, 100, 125, 0))
        self.assertIsNone(module.reward_risk(100, 90, 99, 0))
        self.assertIsNone(module.reward_risk(100, 90, 125, -1))

    def test_screen_excludes_invalid_rows_and_never_issues_buy(self):
        import pandas as pd
        import screener
        self.assertTrue(hasattr(screener, 'screen'), 'Missing first-stage screen')
        base = {'Ticker':'ok', 'Market':'بورس', 'Trade Type':'تابلو', 'Sector':'فلزات',
                'Value':1000000, 'Volume':1000, 'No':600, 'Close':110, 'Final':108,
                'Close(%)':1, 'Day_UL':115, 'EPS':20, 'Vol_Buy_R':800,
                'Vol_Sell_R':400, 'Vol_Buy_I':200, 'Vol_Sell_I':600,
                'No_Buy_R':10, 'No_Sell_R':10}
        rows = [base, dict(base, Ticker='fund', Market='صندوق قابل معامله'),
                dict(base, Ticker='zero', No_Buy_R=0),
                dict(base, Ticker='queue', Close=115),
                dict(base, Ticker='imbalance', Vol_Buy_I=0), base]
        result = screener.screen(pd.DataFrame(rows))
        self.assertEqual(result['unique_rows'], 5)
        self.assertEqual([x['Ticker'] for x in result['shortlist']], ['ok'])
        self.assertFalse(result['buy_signals'])
        self.assertEqual(result['status'], 'preliminary_only')

class AuditRegressions(unittest.TestCase):
    @staticmethod
    def row(**changes):
        base = {'Ticker':'نمونه', 'Name':'شرکت نمونه', 'Market':'بورس', 'Trade Type':'تابلو',
                'Sector':'فلزات', 'Value':1000000, 'Volume':1000, 'No':600,
                'Close':110, 'Final':108, 'Close(%)':1, 'Day_UL':115, 'EPS':20,
                'Vol_Buy_R':800, 'Vol_Sell_R':400, 'Vol_Buy_I':200, 'Vol_Sell_I':600,
                'No_Buy_R':10, 'No_Sell_R':10}
        base.update(changes)
        return base

    def run_screen(self, rows):
        import pandas as pd
        import screener
        return screener.screen(pd.DataFrame(rows))

    def test_real_companies_are_not_excluded_by_name_or_digits(self):
        rows = [self.row(Ticker='بورس', Name='بورس اوراق بهادار تهران'),
                self.row(Ticker='وصندوق', Name='سرمایه گذاری صندوق بازنشستگی'),
                self.row(Ticker='انرژی3', Name='بورس انرژی ایران'),
                self.row(Ticker='فتاح', Name='شرکت آزمایشی با نام ختم به ح')]
        out = self.run_screen(rows)
        self.assertEqual(out['ordinary_rows'], 4)
        self.assertEqual(out['passing_count'], 4)

    def test_funds_detected_by_metadata_not_substring(self):
        out = self.run_screen([self.row(), self.row(Ticker='fund', Name='صندوق س. نمونه'),
             self.row(Ticker='fund2', Sector='صندوق سرمایه گذاری قابل معامله'),
             self.row(Ticker='right', Market='حق تقدم بورس'),
             self.row(Ticker='block', **{'Trade Type':'بلوکی'})])
        self.assertEqual(out['ordinary_rows'], 1)

    def test_queue_is_retained_only_as_watchlist_with_reason(self):
        out = self.run_screen([self.row(Close=115)])
        self.assertEqual(out['passing_count'], 0)
        self.assertEqual(len(out['watchlist']), 1)
        self.assertEqual(out['watchlist'][0]['reason'], 'at_upper_limit_do_not_chase')
        self.assertEqual(out['stage_counts']['positive_return'], 1)
        self.assertEqual(out['stage_counts']['below_upper_limit'], 0)
        self.assertEqual(out['buy_signals'], [])

    def test_conflicting_duplicates_not_arbitrarily_kept(self):
        out = self.run_screen([self.row(), self.row(Close=111)])
        self.assertEqual(out['valid_rows'], 0)
        self.assertEqual(out['quality']['conflicting_symbols'], ['نمونه'])
        self.assertEqual(out['status'], 'insufficient_data')

    def test_empty_input_is_insufficient_not_negative_signal(self):
        import pandas as pd
        import screener
        frame = pd.DataFrame([self.row()]).iloc[:0]
        out = screener.screen(frame)
        self.assertEqual(out['status'], 'insufficient_data')
        self.assertEqual(out['passing_count'], 0)

    def test_missing_eps_is_counted_and_not_treated_as_loss(self):
        out = self.run_screen([self.row(EPS=None)])
        self.assertEqual(out['quality']['invalid_numeric_rows'], 1)
        self.assertEqual(out['status'], 'insufficient_data')

    def test_nonpositive_seller_volume_does_not_create_infinite_power(self):
        out = self.run_screen([self.row(Vol_Sell_R=0, Vol_Sell_I=1000)])
        self.assertEqual(out['valid_rows'], 0)
        self.assertEqual(out['passing_count'], 0)

    def test_above_daily_limit_is_bad_data_not_valid_filter_failure(self):
        out = self.run_screen([self.row(Close=116)])
        self.assertEqual(out['valid_rows'], 0)

class DataIntegrityTests(unittest.TestCase):
    row = staticmethod(AuditRegressions.row)
    run_screen = AuditRegressions.run_screen
    def test_fractional_shares_and_counts_exceeding_shares_are_rejected(self):
        for row in [self.row(Vol_Sell_R=1e-320, Vol_Sell_I=1000),
                    self.row(Volume=1000.5), self.row(No_Buy_R=801, No=900)]:
            with self.subTest(row=row):
                self.assertEqual(self.run_screen([row])['valid_rows'], 0)

    def test_turnover_reconciles_with_available_daily_range(self):
        for row in [self.row(Low=100, High=115, Value=1e30),
                    self.row(Low=111, High=115), self.row(Low=120, High=100)]:
            with self.subTest(row=row):
                self.assertEqual(self.run_screen([row])['valid_rows'], 0)

    def test_explicit_bad_provenance_is_not_shortlisted(self):
        for row in [self.row(Currency='تومان'), self.row(State='متوقف'),
                    self.row(InstrumentType='rights')]:
            with self.subTest(row=row):
                self.assertEqual(self.run_screen([row])['passing_count'], 0)

class RuntimeRegressions(unittest.TestCase):
    def test_download_worker_timeout_is_bounded(self):
        import screener
        import tempfile
        from unittest.mock import patch
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 2)) as run:
                with self.assertRaises(TimeoutError):
                    screener.download_market(d, timeout=2)
                self.assertEqual(run.call_args.kwargs['timeout'], 2)

    def test_failed_cli_replaces_stale_success_output(self):
        import screener
        import tempfile
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'screen.json'
            p.write_text('{"status":"preliminary_only","shortlist":[{"Ticker":"stale"}]}')
            with patch('sys.argv', ['screener', '--market-csv', str(Path(d)/'missing.csv'), '--out', d]):
                result = screener.main()
            self.assertEqual(result, 2)
            saved = json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'insufficient_data')
            self.assertEqual(saved['shortlist'], [])
            self.assertEqual(saved['buy_signals'], [])
            self.assertIn('error', saved)

if __name__ == '__main__':
    unittest.main()
