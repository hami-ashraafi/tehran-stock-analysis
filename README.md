# Tehran Stock Analysis (tehran-stock-analysis)

Conservative Tehran Stock Exchange (TSETMC) screening and analysis modules for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

**Status: research tooling only — not investment advice, not a profitable validated strategy.**

## What it does

| Module | Purpose |
|---|---|
| `scripts/screener.py` | First-stage market screen: ordinary-share universe, data-quality gates, liquidity rank, upper-limit watchlist |
| `scripts/market_core.py` | Exchange-published session date (`marketActivityDEven`), market state, index context, symbol→insCode identity, rights detection |
| `scripts/analysis_core.py` | EMA20/50/200, Wilder RSI14, MACD on declared price basis; confirmed-pivot S/R; client-type flow metrics (buyer power, net individual/corporate value) |
| `scripts/codal_core.py` | Codal report search: own-issuer filtering, consolidated/period detection, magic-byte format detection (Codal serves HTML as `.xlsx`) |
| `scripts/decision_core.py` | Fail-closed final gate: a buy verdict requires all 10 checks with source+date evidence matching the exchange session |
| `scripts/backtest_core.py` | Exploratory technical backtest (EMA20/50 + RSI14, next-open fill, explicit fees/slippage, 20-session hold) |

Plus `SKILL.md` — the Hermes skill definition with the full agent procedure, and `references/research-and-validation.md` — evidence notes and validation requirements.

## Backtest reality check (8 liquid symbols, ~1 year, 103 trades)

| Metric | Strategy | Buy & hold |
|---|---|---|
| Avg return | **+3.2%** | **+170.9%** |
| Beat buy&hold | 0 / 8 symbols | — |
| Win rate | 50.5% | — |

The fixed technical proxy underperforms severely in a rising market: signals fire late, costs compound, and the 20-session exit cuts winners. In down-markets its value is loss *limiting* (lower drawdowns on most symbols), not profit generation. Details in `C:/.../scratch/tse-backtest/summary.json` pattern — see `scripts/backtest_core.py` caveats.

## Design principles

- **Fail-closed**: missing or unverifiable data → verdict `unknown` / `wait`, never a buy.
- **Session-date integrity**: the exchange's own `marketActivityDEven` stamp is the reference; local download clocks are not trusted.
- **Entity separation**: Codal subsidiaries publish under a parent's symbol; filtering is by exact `CompanyName`, and title mentions alone are never treated as proof.
- **No lookahead**: indicator windows and volume baselines are prior-only; pivots require later confirmation bars.
- **Bounded I/O**: legacy library calls run in subprocesses with timeouts; failures replace stale results instead of leaving them looking current.

## Requirements

- Python 3.11+ (developed on 3.11, pandas 3.x)
- `pytse-client` 0.19+, `finpy-tse` 1.2+, `pandas`, `requests`

## Tests

```bash
python -m unittest discover -s scripts -p 'test_*.py'
```

70 synthetic unit tests. Test fixtures are constructed data, never market evidence.

## Usage (inside Hermes Agent)

Install as a skill directory under `~/.hermes/skills/tehran-stock-analysis/`, then:

- `تحلیل کن [نماد]` — full single-ticker analysis (technical + tape + fundamentals)
- `فرصت خرید پیدا کن` — market screen producing at most 3 fully-checked candidates

## License

MIT
