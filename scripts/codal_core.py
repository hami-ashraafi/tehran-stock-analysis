"""Codal report search, own-issuer filtering and financial extraction.

Identity rule (learned from the Mellat failure): Symbol AND CompanyName do NOT
prove ownership. Subsidiaries publish under the parent's symbol, and the parent
name can appear inside a subsidiary's title. Therefore:
  1. Letters are filtered by exact CompanyName == issuer's own registered name.
  2. A subsidiary name appearing in the TITLE is noted, not used for filtering.
  3. Final verification requires the reporting entity inside the report body.

File-format rule: Codal ExcelUrl returns HTML disguised as .xlsx. The format is
detected from magic bytes, never from the extension.
"""
import re

SEARCH_URL = 'https://search.codal.ir/api/search/v2/q'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
INTERIM_KEYWORD = 'میاندوره'
MONTHLY_KEYWORD = 'ماهانه'
CONSOLIDATED_KEYWORD = 'تلفیقی'
PERIOD_RE = re.compile(r'(?:۳|۶|۹)\s*ماهه\s*منتهی\s*به\s*[\d۰-۹/]{8,10}')
NET_PROFIT_LABELS = ('سود (زیان) خالص', 'سود (زيان) خالص', 'سود خالص')


def _get_json(url, timeout=25):
    import requests
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
    except Exception:
        return None
    if r.status_code != 200 or 'json' not in r.headers.get('Content-Type', ''):
        return None
    try:
        return r.json()
    except Exception:
        return None


def search_letters(symbol, issuer_name, *, max_pages=5, timeout=25):
    """Own-issuer letters only; bounded pagination with repeated-page stop."""
    letters, seen_pages = [], set()
    for page in range(1, max_pages + 1):
        url = (f'{SEARCH_URL}?Page={page}&PageSize=200&chartType=0'
               f'&Audited=true&Symbol={symbol}')
        payload = _get_json(url, timeout=timeout)
        if not isinstance(payload, dict):
            return []
        body = payload.get('Letters')
        if not isinstance(body, list):
            return []
        page_signature = tuple((l.get('TracingNo'), l.get('PublishDateTime')) for l in body)
        if page_signature in seen_pages:
            break
        seen_pages.add(page_signature)
        letters.extend(l for l in body if isinstance(l, dict))
        if len(letters) >= int(payload.get('Total') or 0):
            break
    return [l for l in letters if str(l.get('CompanyName', '')).strip() == issuer_name]


def _period_label(title):
    match = re.search(r'(?:۳|۶|۹)\s*ماهه\s*منتهی\s*به\s*[\d۰-۹/]{8,10}', title)
    return match.group(0).replace('  ', ' ').strip() if match else None


def select_reports(symbol, issuer_name, *, max_pages=5, timeout=25):
    """Latest own-issuer interim and monthly activity letters."""
    letters = search_letters(symbol, issuer_name, max_pages=max_pages, timeout=timeout)
    letters.sort(key=lambda l: str(l.get('PublishDateTime', '')), reverse=True)
    interim = next((l for l in letters if INTERIM_KEYWORD in l.get('Title', '')), None)
    monthly = next((l for l in letters if MONTHLY_KEYWORD in l.get('Title', '')), None)

    def enrich(l):
        if l is None:
            return None
        title = l.get('Title', '')
        out = dict(l)
        out['title_mentions_consolidated'] = CONSOLIDATED_KEYWORD in title
        out['period_label'] = _period_label(title)
        return out

    return {'interim': enrich(interim), 'monthly': enrich(monthly),
            'issuer': issuer_name, 'letters_found': len(letters)}


def detect_format(content: bytes) -> str:
    """Detect actual file format from magic bytes, not extension."""
    if not isinstance(content, (bytes, bytearray)) or len(content) < 4:
        return 'unknown'
    if content.startswith(b'PK\x03\x04'):
        return 'xlsx'
    if content.startswith(b'\xd0\xcf\x11\xe0'):
        return 'xls'
    head = content[:512].lstrip().lower()
    if head.startswith(b'<!doctype html') or head.startswith(b'<html') or b'<table' in head:
        return 'html'
    return 'unknown'


def extract_line_items(rows):
    """Extract known P&L line items from label/value row dicts (Persian labels)."""
    items = {}
    for row in rows:
        label = str(row.get('label', '')).strip()
        value = row.get('value')
        if label in NET_PROFIT_LABELS:
            items['net_profit'] = value
    return items
