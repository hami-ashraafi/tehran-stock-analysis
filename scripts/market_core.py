"""Source-backed TSETMC session date and instrument identity.

Why this module exists: a local download clock does NOT prove which exchange
session the data belongs to. Everything here is derived from fields the
exchange itself publishes:

  * `marketActivityDEven` -- the exchange's own market-activity date stamp
    (Gregorian YYYYMMDD) from the public market-overview endpoint.
  * `marketStateTitle`    -- textual market state; 'بسته' means closed, so the
    session is complete. Any other state is treated as not-complete.
  * instrument search     -- maps a user symbol to an authoritative insCode and
    reveals rights/other non-ordinary instruments.

Limitations (do not overstate):
  * `marketStateTitle` is a market-wide state, NOT per-symbol halt status. A
    single symbol can be suspended while the market is open; that must be
    verified separately before trading conclusions.
  * The search endpoint does not return ISIN here, so `is_ordinary_share` is a
    conservative heuristic from the symbol/name shape plus market flow, not a
    legal instrument-type certification.
  * No request is retried more than once. Failure yields verified=False; it
    never yields a guessed date.
"""
import re

BASE = 'https://cdn.tsetmc.com/api'
OVERVIEW_URL = BASE + '/MarketData/GetMarketOverview/1'
SEARCH_URL = BASE + '/Instrument/GetInstrumentSearch/{symbol}'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
CLOSED_STATES = ('بسته',)
# Arabic -> Persian letter folding; TSETMC mixes both encodings.
FOLD = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ۀ': 'ه', 'ة': 'ه', '\u200c': ''})


def _get(url, timeout=20):
    import requests
    return requests.get(url, headers=HEADERS, timeout=timeout)


def _json(url, timeout=20):
    """Bounded fetch; returns None instead of raising so callers stay fail-closed."""
    try:
        response = _get(url, timeout=timeout)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    if 'json' not in response.headers.get('Content-Type', ''):
        return None
    try:
        return response.json()
    except Exception:
        return None


def parse_deven(value):
    """Convert the exchange's YYYYMMDD stamp to an ISO date, else None."""
    try:
        text = str(int(value))
    except (TypeError, ValueError):
        return None
    if len(text) != 8:
        return None
    year, month, day = int(text[:4]), int(text[4:6]), int(text[6:])
    try:
        from datetime import date
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalise(symbol):
    return str(symbol or '').translate(FOLD).strip()


def _context(overview):
    index = overview.get('indexLastValue')
    change = overview.get('indexChange')
    eq_index = overview.get('indexEqualWeightedLastValue')
    eq_change = overview.get('indexEqualWeightedChange')
    values = (index, change, eq_index, eq_change)
    if any(not isinstance(v, (int, float)) for v in values):
        return None
    prev, eq_prev = index - change, eq_index - eq_change
    if prev <= 0 or eq_prev <= 0:
        return None
    pct = 100.0 * change / prev
    eq_pct = 100.0 * eq_change / eq_prev
    direction = 'up' if eq_pct > 0 else ('down' if eq_pct < 0 else 'flat')
    return {'index_change_pct': round(pct, 3),
            'equal_weighted_change_pct': round(eq_pct, 3),
            'breadth_direction': direction}


def fetch_market_session(timeout=20):
    """Return the exchange-published session date, state and index context."""
    result = {'session': None, 'market_state': None, 'completed_session': False,
              'verified': False, 'context': None, 'source': OVERVIEW_URL}
    payload = _json(OVERVIEW_URL, timeout=timeout)
    if not isinstance(payload, dict):
        result['reason'] = 'overview_unavailable'
        return result
    overview = payload.get('marketOverview')
    if not isinstance(overview, dict):
        result['reason'] = 'unexpected_schema'
        return result
    session = parse_deven(overview.get('marketActivityDEven'))
    state = overview.get('marketStateTitle')
    result['market_state'] = state if isinstance(state, str) else None
    result['context'] = _context(overview)
    if session is None:
        result['reason'] = 'no_exchange_date'
        return result
    result['session'] = session
    result['verified'] = True
    result['completed_session'] = result['market_state'] in CLOSED_STATES
    if not result['completed_session']:
        result['reason'] = 'session_in_progress_or_unknown_state'
    return result


def _is_ordinary(symbol, name):
    """Conservative shape test: reject rights, blocks and non-board variants."""
    if re.search(r'ح$', symbol) or name.startswith('ح .') or name.startswith('ح.'):
        return False
    if re.search(r'\d$', symbol):          # 2=block, 3=compensatory, 4=wholesale
        return False
    return True


def resolve_identity(symbol, timeout=20):
    """Map a symbol to one authoritative insCode; ambiguity blocks the result."""
    wanted = normalise(symbol)
    url = SEARCH_URL.format(symbol=wanted)
    result = {'symbol': wanted, 'ins_code': None, 'name': None, 'market': None,
              'is_ordinary_share': False, 'verified': False, 'source': url}
    if not wanted:
        result['reason'] = 'empty_symbol'
        return result
    payload = _json(url, timeout=timeout)
    if not isinstance(payload, dict):
        result['reason'] = 'search_unavailable'
        return result
    rows = payload.get('instrumentSearch')
    if not isinstance(rows, list):
        result['reason'] = 'unexpected_schema'
        return result
    matches = [r for r in rows if isinstance(r, dict)
               and normalise(r.get('lVal18AFC')) == wanted]
    if not matches:
        result['reason'] = 'symbol_not_found'
        return result
    codes = {str(r.get('insCode')) for r in matches}
    if len(codes) != 1:
        result['reason'] = 'ambiguous_symbol'
        return result
    row = matches[0]
    name = normalise(row.get('lVal30'))
    result.update({'ins_code': str(row.get('insCode')), 'name': name,
                   'market': row.get('flowTitle'),
                   'board': row.get('cgrValCot'),
                   'is_ordinary_share': _is_ordinary(wanted, name),
                   'verified': True})
    return result
