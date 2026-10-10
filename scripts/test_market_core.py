"""Synthetic market-identity tests. Network calls are mocked; no live evidence."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


def load():
    p = Path(__file__).with_name('market_core.py')
    assert p.exists(), 'Missing market_core.py'
    spec = importlib.util.spec_from_file_location('market_core', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeResponse:
    def __init__(self, payload, status=200, ctype='application/json; charset=utf-8'):
        self._payload = payload
        self.status_code = status
        self.headers = {'Content-Type': ctype}
        self.text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)

    def json(self):
        if not isinstance(self._payload, dict):
            raise ValueError('not json')
        return self._payload


OVERVIEW = {'marketOverview': {'marketActivityDEven': 20261010, 'marketStateTitle': 'بسته',
                               'indexLastValue': 8265478.36, 'indexChange': 134398.75,
                               'indexEqualWeightedLastValue': 2172524.23,
                               'indexEqualWeightedChange': 22092.05}}
SEARCH = {'instrumentSearch': [
    {'insCode': '778253364357513', 'lVal30': 'بانك ملت', 'lVal18AFC': 'وبملت',
     'flow': 1, 'flowTitle': 'بازار بورس', 'cgrValCot': 'N1', 'lastDate': 1},
    {'insCode': '25043059770705816', 'lVal30': 'ح . بانك ملت', 'lVal18AFC': 'وبملتح',
     'flow': 1, 'flowTitle': 'بازار بورس', 'cgrValCot': 'N1', 'lastDate': 1}]}


class SessionTests(unittest.TestCase):
    def test_deven_parsed_as_exchange_session_not_local_clock(self):
        m = load()
        self.assertEqual(m.parse_deven(20261010), '2026-10-10')
        for bad in [0, None, 'x', 2026101, 99999999]:
            self.assertIsNone(m.parse_deven(bad))

    def test_market_session_reports_state_and_source(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(OVERVIEW)):
            out = m.fetch_market_session()
        self.assertEqual(out['session'], '2026-10-10')
        self.assertEqual(out['market_state'], 'بسته')
        self.assertTrue(out['completed_session'])
        self.assertIn('tsetmc.com', out['source'])
        self.assertTrue(out['verified'])

    def test_open_market_is_not_a_completed_session(self):
        m = load()
        payload = {'marketOverview': dict(OVERVIEW['marketOverview'], marketStateTitle='مجاز')}
        with patch.object(m, '_get', return_value=FakeResponse(payload)):
            out = m.fetch_market_session()
        self.assertFalse(out['completed_session'])
        self.assertTrue(out['verified'])

    def test_missing_deven_is_unverified_not_guessed(self):
        m = load()
        payload = {'marketOverview': {'marketActivityDEven': 0, 'marketStateTitle': 'بسته'}}
        with patch.object(m, '_get', return_value=FakeResponse(payload)):
            out = m.fetch_market_session()
        self.assertIsNone(out['session'])
        self.assertFalse(out['verified'])
        self.assertFalse(out['completed_session'])

    def test_http_failure_is_unverified_never_raises(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse('<html>', status=500, ctype='text/html')):
            out = m.fetch_market_session()
        self.assertFalse(out['verified'])
        self.assertIsNone(out['session'])


class IdentityTests(unittest.TestCase):
    def test_exact_symbol_match_returns_ordinary_share(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(SEARCH)):
            out = m.resolve_identity('وبملت')
        self.assertEqual(out['ins_code'], '778253364357513')
        self.assertEqual(out['symbol'], 'وبملت')
        self.assertTrue(out['is_ordinary_share'])
        self.assertTrue(out['verified'])

    def test_rights_symbol_is_not_ordinary_share(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(SEARCH)):
            out = m.resolve_identity('وبملتح')
        self.assertFalse(out['is_ordinary_share'])

    def test_arabic_persian_letters_normalised_before_matching(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(SEARCH)):
            out = m.resolve_identity('وبملت')   # ARABIC YEH/KAF variants
        self.assertEqual(out['ins_code'], '778253364357513')

    def test_unknown_symbol_is_unverified_not_nearest_match(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(SEARCH)):
            out = m.resolve_identity('فملی')
        self.assertFalse(out['verified'])
        self.assertIsNone(out['ins_code'])

    def test_ambiguous_duplicate_symbols_block_identity(self):
        m = load()
        dup = {'instrumentSearch': SEARCH['instrumentSearch'] + [
            dict(SEARCH['instrumentSearch'][0], insCode='999')]}
        with patch.object(m, '_get', return_value=FakeResponse(dup)):
            out = m.resolve_identity('وبملت')
        self.assertFalse(out['verified'])
        self.assertEqual(out['reason'], 'ambiguous_symbol')


class ContextTests(unittest.TestCase):
    def test_market_context_uses_both_indices(self):
        m = load()
        with patch.object(m, '_get', return_value=FakeResponse(OVERVIEW)):
            out = m.fetch_market_session()
        ctx = out['context']
        self.assertGreater(ctx['index_change_pct'], 0)
        self.assertGreater(ctx['equal_weighted_change_pct'], 0)
        self.assertEqual(ctx['breadth_direction'], 'up')

    def test_context_is_none_when_index_values_missing(self):
        m = load()
        payload = {'marketOverview': {'marketActivityDEven': 20261010, 'marketStateTitle': 'بسته'}}
        with patch.object(m, '_get', return_value=FakeResponse(payload)):
            out = m.fetch_market_session()
        self.assertIsNone(out['context'])


if __name__ == '__main__':
    unittest.main()
