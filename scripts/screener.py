"""Conservative TSE shortlist helper. A shortlist is never a buy signal."""
import math


def reward_risk(entry, stop, target, cost=0):
    vals = (entry, stop, target, cost)
    if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in vals):
        return None
    if not (target > entry > stop > 0) or cost < 0:
        return None
    return (target - entry - cost) / (entry - stop + cost)


def screen(frame):
    import pandas as pd
    df = frame.copy()
    if 'Ticker' not in df:
        df = df.reset_index()
    required = ['Ticker', 'Market', 'Trade Type', 'Value', 'Volume', 'No',
                'Close', 'Final', 'Close(%)', 'Day_UL', 'EPS', 'Vol_Buy_R',
                'Vol_Sell_R', 'Vol_Buy_I', 'Vol_Sell_I', 'No_Buy_R', 'No_Sell_R']
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError('Missing columns: ' + ', '.join(missing))
    initial = len(df)
    # Identical rows are safe to deduplicate; conflicting snapshots need provenance.
    unique = int(df['Ticker'].nunique(dropna=True))
    exact = df.drop_duplicates().copy()
    conflicts = sorted(exact.loc[exact['Ticker'].duplicated(keep=False), 'Ticker'].dropna().astype(str).unique().tolist())
    df = exact[~exact['Ticker'].isin(conflicts)].copy()
    numeric = required[3:]
    for key in numeric:
        df[key] = pd.to_numeric(df[key], errors='coerce')
    has_ticker = df['Ticker'].notna() & df['Ticker'].astype(str).str.strip().ne('')
    ordinary = (has_ticker & df['Market'].isin(['بورس', 'فرابورس']) & df['Trade Type'].eq('تابلو'))
    # Fund metadata is authoritative; issuer names may legitimately contain صندوق/اوراق.
    if 'Name' in df:
        ordinary &= ~df['Name'].fillna('').astype(str).str.strip().str.match(r'^(?:صندوق\b|اختیار\b|اوراق\b|حق\s*تقدم\b)')
    if 'Sector' in df:
        ordinary &= ~df['Sector'].fillna('').astype(str).str.contains('صندوق سرمایه گذاری قابل معامله', regex=False)
    excluded_universe = df.loc[~ordinary, 'Ticker'].dropna().astype(str).tolist()
    df = df[ordinary].copy()
    ordinary_n = len(df)
    finite = df[numeric].apply(lambda s: s.map(lambda v: pd.notna(v) and math.isfinite(v))).all(axis=1)
    positive_cols = ['Value','Volume','No','Close','Final','Day_UL','No_Buy_R','No_Sell_R','Vol_Buy_R','Vol_Sell_R']
    structural = ((df[positive_cols] > 0).all(axis=1)
                  & (df[['Vol_Buy_I','Vol_Sell_I']] >= 0).all(axis=1)
                  & (df['Close'] <= df['Day_UL']) & (df['Final'] <= df['Day_UL']))
    count_cols = ['No','No_Buy_R','No_Sell_R']
    structural &= (df[count_cols].mod(1) == 0).all(axis=1)
    structural &= (df['No_Buy_R'] <= df['No']) & (df['No_Sell_R'] <= df['No'])
    shares = ['Volume','Vol_Buy_R','Vol_Sell_R','Vol_Buy_I','Vol_Sell_I']
    structural &= (df[shares].mod(1) == 0).all(axis=1)
    structural &= (df['No_Buy_R'] <= df['Vol_Buy_R']) & (df['No_Sell_R'] <= df['Vol_Sell_R'])
    structural &= df['No'] <= df['Volume']
    if 'Low' in df and 'High' in df:
        low = pd.to_numeric(df['Low'], errors='coerce')
        high = pd.to_numeric(df['High'], errors='coerce')
        avg = df['Value'] / df['Volume']
        structural &= (low > 0) & (high >= low) & (df['Close'] >= low) & (df['Close'] <= high)
        # Small rounding tolerance; this does not verify currency provenance.
        structural &= (avg >= low * 0.99) & (avg <= high * 1.01)
    for field, accepted in [('Currency', ['IRR','ریال']),
                            ('State', ['مجاز','A']),
                            ('InstrumentType', ['ordinary_share','سهام عادی'])]:
        if field in df:
            structural &= df[field].isin(accepted)
    tolerance = df['Volume'] * 0.01 + 1
    balanced = (((df['Vol_Buy_R'] + df['Vol_Buy_I'] - df['Volume']).abs() <= tolerance)
                & ((df['Vol_Sell_R'] + df['Vol_Sell_I'] - df['Volume']).abs() <= tolerance))
    valid = finite & structural & balanced
    quality = {'identical_duplicate_rows': initial - len(exact), 'conflicting_symbols': conflicts,
               'invalid_numeric_rows': int((~finite).sum()),
               'invalid_structure_rows': int((finite & ~structural).sum()),
               'unbalanced_rows': int((finite & structural & ~balanced).sum()),
               'invalid_symbols': df.loc[~valid, 'Ticker'].astype(str).tolist()}
    df = df[valid].copy()
    valid_n = len(df)
    cutoff = float(df['Value'].quantile(0.75)) if valid_n else None
    df['buyer_power'] = (df['Vol_Buy_R'] / df['No_Buy_R']) / (df['Vol_Sell_R'] / df['No_Sell_R'])
    df['net_individual_volume'] = df['Vol_Buy_R'] - df['Vol_Sell_R']
    checks = [('liquidity', df['Value'] >= (cutoff if cutoff is not None else math.inf)),
              ('trades', df['No'] >= 500), ('positive_eps', df['EPS'] > 0),
              ('buyer_power', df['buyer_power'] >= 1.5), ('positive_flow', df['net_individual_volume'] > 0),
              ('last_vs_final', df['Close'] >= df['Final']), ('positive_return', df['Close(%)'] > 0)]
    mask = pd.Series(True, index=df.index, dtype=bool)
    stages = {}
    exclusions = {}
    for label, condition in checks:
        exclusions[label] = df.loc[mask & ~condition, 'Ticker'].astype(str).tolist()
        mask &= condition
        stages[label] = int(mask.sum())
    watch = df[mask & df['Close'].eq(df['Day_UL'])].sort_values(['Value','Ticker'], ascending=[False,True]).copy()
    watch['reason'] = 'at_upper_limit_do_not_chase'
    exclusions['below_upper_limit'] = watch['Ticker'].astype(str).tolist()
    mask &= df['Close'] < df['Day_UL']
    stages['below_upper_limit'] = int(mask.sum())
    candidates = df[mask].sort_values(['Value','Ticker'], ascending=[False,True])
    cols = ['Ticker','Market','Value','Volume','No','Close','Final','EPS','buyer_power','net_individual_volume']
    return {'status':'preliminary_only' if valid_n else 'insufficient_data',
            'input_rows':initial, 'unique_rows':unique, 'ordinary_rows':ordinary_n, 'valid_rows':valid_n,
            'quality':quality, 'excluded_universe':excluded_universe,
            'stage_counts':stages, 'stage_exclusions':exclusions,
            'liquidity_cutoff_rial':cutoff, 'passing_count':len(candidates),
            'shortlist':candidates[cols].to_dict('records'),
            'watchlist':watch[cols + ['reason']].to_dict('records'), 'buy_signals':[],
            'required_pending':['exchange session/date','instrument identity/status','historical liquidity',
                'adjusted technicals','multi-session flow','issuer Codal statements',
                'market/sector context','executable entry and net reward/risk'],
            'source_session_verified':False}


def download_market(directory, timeout=90):
    """Bound the whole legacy library call, which has no request timeouts."""
    import subprocess
    import sys
    from pathlib import Path
    import pandas as pd
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    worker = (
        "import sys;from pathlib import Path;import finpy_tse;"
        "p=Path(sys.argv[1]);m,o=finpy_tse.Get_MarketWatch(save_excel=False);"
        "m.to_csv(p/'market.csv',encoding='utf-8-sig');"
        "o.to_csv(p/'orders.csv',encoding='utf-8-sig')"
    )
    try:
        subprocess.run([sys.executable, '-c', worker, str(out.resolve())],
                       check=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError('Market download exceeded bounded runtime') from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('Market download failed; no snapshot accepted') from exc
    return pd.read_csv(out / 'market.csv')


def main():
    import argparse
    import datetime
    import json
    import tempfile
    from pathlib import Path
    import pandas as pd
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--live', action='store_true')
    group.add_argument('--market-csv')
    parser.add_argument('--out', required=True)
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {'status':'insufficient_data', 'shortlist':[], 'watchlist':[],
              'buy_signals':[], 'source_session_verified':False}
    code = 2
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError('timeout must be positive and finite')
        if args.live:
            # Isolate each attempt: a timed-out run cannot reuse old CSV files.
            with tempfile.TemporaryDirectory(prefix='download-', dir=out) as d:
                frame = download_market(d, timeout=args.timeout)
                for name in ['market.csv', 'orders.csv']:
                    (Path(d) / name).replace(out / name)
        else:
            frame = pd.read_csv(args.market_csv)
        result = screen(frame)
        code = 0 if result['status'] == 'preliminary_only' else 2
    except Exception as exc:
        result['error'] = {'type':type(exc).__name__, 'message':str(exc)[:500]}
    result['processed_at'] = datetime.datetime.now().astimezone().isoformat()
    result['source'] = 'finpy_tse.Get_MarketWatch' if args.live else str(Path(args.market_csv).resolve())
    temp = out / 'screen.pending.json'
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(out / 'screen.json')
    summary = {k:v for k,v in result.items() if k not in ['shortlist','watchlist','stage_exclusions','excluded_universe']}
    summary['watchlist_count'] = len(result['watchlist'])
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == '__main__':
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
