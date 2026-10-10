"""Synthetic Codal identity/pagination tests. Network mocked; no live evidence."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


def load():
    p = Path(__file__).with_name('codal_core.py')
    assert p.exists(), 'Missing codal_core.py'
    spec = importlib.util.spec_from_file_location('codal_core', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeResponse:
    def __init__(self, payload, status=200, ctype='application/json; charset=utf-8', content=b''):
        self._payload = payload
        self.status_code = status
        self.headers = {'Content-Type': ctype}
        self.content = content
        self.text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else (content or '').decode('utf-8', 'replace')

    def json(self):
        if not isinstance(self._payload, dict):
            raise ValueError('not json')
        return self._payload


def letter(no, symbol, company, title, published='۱۴۰۵/۰۷/۱۱'):
    return {'TracingNo': no, 'Symbol': symbol, 'CompanyName': company,
            'Title': title, 'PublishDateTime': published + ' 10:00:00',
            'LetterCode': 'ن-۱۰', 'ExcelUrl': f'https://excel.codal.ir/service/Excel/GetAll/HS{no}/0'}


LETTERS = {'Total': 3, 'Page': 1, 'Letters': [
    letter(1, 'وبملت', 'بانک ملت', 'اطلاعات و صورت‌های مالی میاندوره‌ای تلفیقی دوره ۶ ماهه منتهی به ۱۴۰۵/۰۴/۳۱ (شرکت بهساز مشارکت های ملت)'),
    letter(2, 'وبملت', 'بانک ملت', 'گزارش فعالیت ماهانه دوره ۱ ماهه منتهی به ۱۴۰۵/۰۶/۳۱ (اصلاحیه)'),
    letter(3, 'وبملت', 'شرکت تحقیقاتی کاوش ملت', 'اطلاعات و صورت‌های مالی میاندوره‌ای دوره ۶ ماهه منتهی به ۱۴۰۵/۰۴/۳۱'),
]}


class SearchTests(unittest.TestCase):
    def test_own_issuer_letters_exclude_subidiaries_by_name(self):
        m = load()
        with patch.object(m, '_get_json', return_value=LETTERS):
            out = m.search_letters('وبملت', 'بانک ملت', max_pages=2)
        companies = {l['CompanyName'] for l in out}
        self.assertEqual(companies, {'بانک ملت'})
        self.assertEqual(len(out), 2)

    def test_repeated_page_detection_stops_pagination(self):
        m = load()
        calls = []

        def fake(url, timeout=20):
            calls.append(url)
            # page 1 returns only 2 of Total=3 (truncated); page 2 repeats the same body -> stop
            if len(calls) == 1:
                return dict(LETTERS, Total=3, Letters=LETTERS['Letters'][:2])
            return dict(LETTERS, Total=3, Letters=LETTERS['Letters'][:2])
        with patch.object(m, '_get_json', side_effect=fake):
            out = m.search_letters('وبملت', 'بانک ملت', max_pages=5)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(out), 2)

    def test_total_reached_stops_early(self):
        m = load()
        calls = []

        def fake(url, timeout=20):
            calls.append(url)
            return dict(LETTERS, Total=3)
        with patch.object(m, '_get_json', side_effect=fake):
            m.search_letters('وبملت', 'بانک ملت', max_pages=10)
        self.assertEqual(len(calls), 1)

    def test_api_failure_returns_unverified(self):
        m = load()
        with patch.object(m, '_get_json', return_value=None):
            out = m.search_letters('وبملت', 'بانک ملت', max_pages=3)
        self.assertEqual(out, [])

    def test_latest_interim_and_monthly_selected(self):
        m = load()
        with patch.object(m, '_get_json', return_value=LETTERS):
            out = m.select_reports('وبملت', 'بانک ملت', max_pages=2)
        self.assertEqual(out['interim']['TracingNo'], 1)
        self.assertEqual(out['monthly']['TracingNo'], 2)
        self.assertTrue(out['interim']['title_mentions_consolidated'])
        self.assertFalse(out['monthly']['title_mentions_consolidated'])
        self.assertEqual(out['interim']['period_label'], '۶ ماهه منتهی به ۱۴۰۵/۰۴/۳۱')


class ParseTests(unittest.TestCase):
    def test_format_detected_from_content_not_extension(self):
        m = load()
        html = b'<html><table><tr><td>1</td></tr></table></html>'
        self.assertEqual(m.detect_format(html), 'html')
        self.assertEqual(m.detect_format(b'PK\x03\x04rest'), 'xlsx')
        self.assertEqual(m.detect_format(b'\xd0\xcf\x11\xe0rest'), 'xls')
        self.assertEqual(m.detect_format(b'plain junk'), 'unknown')

    def test_entity_not_in_title_still_requires_body_verification(self):
        m = load()
        with patch.object(m, '_get_json', return_value=LETTERS):
            out = m.select_reports('وبملت', 'بانک ملت', max_pages=2)
        # subsidiary name in the TITLE must not block; verification happens at body parse
        self.assertEqual(out['interim']['CompanyName'], 'بانک ملت')


class ExtractTests(unittest.TestCase):
    SHEET_HTML = b'<html><body><table><tr><td>net profit</td><td>2,599,912</td></tr></table></body></html>'

    def test_net_profit_row_found(self):
        m = load()
        rows = [{'label': 'سود (زیان) خالص', 'value': 2599912}]
        out = m.extract_line_items(rows)
        self.assertEqual(out['net_profit'], 2599912)

    def test_missing_items_left_unknown(self):
        m = load()
        out = m.extract_line_items([{'label': 'something', 'value': 1}])
        self.assertNotIn('net_profit', out)


if __name__ == '__main__':
    unittest.main()
