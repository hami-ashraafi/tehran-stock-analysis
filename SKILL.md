---
name: tehran-stock-analysis
description: Use for TSE analysis or «فرصت خرید پیدا کن» screening.
version: 2.2.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [tse, screening, finance, persian]
    related_skills: [grounded-citations]
---

# تحلیل و غربالگری محافظه‌کار بورس ایران

## When to Use
- `تحلیل کن [نماد]`: analyze the supplied Iranian ordinary-share ticker.
- `فرصت خرید پیدا کن`: screen ordinary shares across Tehran exchange and main Farabourse markets; no fixed industry.
- Also load for requests to improve or inspect this workflow. Do not require magic wording when intent is clear.
- Default horizon: 1–4 weeks. Default screening risk: conservative, liquid shares, fewer better-supported candidates.
- Runs are ON DEMAND only. No cron, subscriptions, broker access or trades without separate authorization.

## Output contract
Answer in simple Persian, usually under 150 words. Do the research internally; no running technical narration, raw rows, log dumps or unsolicited files.
- Single ticker: first line `بخر / نخر / صبر کن / نامشخص` (qualified, not a guarantee), then exactly five short table rows: قیمت و روند، تابلو، بنیاد، ریسک، نتیجه. Use نگهدار/بفروش only when the user actually owns the stock and evidence supports that advice.
- Screening: one verdict line and up to THREE rows: نماد | وضعیت و دلیل کوتاه | ورود / حد ضرر / هدف. Never pad the list. State source session/date and price unit, with compact source links.
- If complete checks find no qualifying opportunity: `فعلاً خریدی پیشنهاد نمی‌کنم.`
- If required data are unavailable: `نتیجه نامشخص است؛ [missing dataset].` Never silently score missing data as neutral or call an incomplete scan a market-wide absence of opportunity.
- Preliminary names are `زیر نظر؛ نه سیگنال خرید`. Omit unsupported price levels.
- Keep operational output in chat, not Markdown reports. JSON/CSV evidence and skill reference files are permitted.

## Prerequisites
Use `terminal` to discover the Python environment, package versions, current Tehran date/time and active skill path. The local `C:/tmp/tse-env/Scripts/python.exe` has previously worked with pytse-client, finpy-tse, pandas and jdatetime; check existence/imports before reuse. Prefer a uv Python 3.11 environment for older binary dependencies. Use the Hermes scratch directory for temporary data, never the system temp directory. Do not reinstall global packages unnecessarily.
Read `references/research-and-validation.md` when changing interpretation or thresholds. This workflow is a conservative heuristic, NOT a backtested profitable system.

## Implemented scope and limitations
- Executable modules (all tested, 70 synthetic unit tests):
  - `scripts/screener.py` — first-stage market screen, data-quality gates, upper-limit watchlist, reward/risk arithmetic.
  - `scripts/market_core.py` — exchange-published session date (`marketActivityDEven`), market state, index context, symbol→insCode identity with rights detection. Verified live on وبملت/فملی/وبملتح.
  - `scripts/analysis_core.py` — `analyze_history(raw, adj, price_basis=...)` → EMA20/50/200, Wilder RSI14, MACD, confirmed-pivot levels on raw scale, prior-only volume baselines, gap/quality diagnostics. `analyze_flow(ct)` → dated numeric-validated client-type metrics: buyer power, net individual/corporate volume+value 5d/20d, per-capita prior baselines. Verified live on وبملت.
  - `scripts/codal_core.py` — `select_reports(symbol, issuer_name)` → latest own-issuer interim/monthly with consolidated flag and period label; bounded pagination with repeated-page stop; magic-byte format detection (Codal ExcelUrl returns HTML disguised as .xlsx — verified live). `search_letters` filters by exact CompanyName; title-only subsidiary mentions are NOT used as filter.
  - `scripts/decision_core.py` — `evaluate(case, as_of=...)` fail-closed final gate: all 10 checks must carry source+date evidence matching the reference session; any missing/invalid → `unknown`; negative gate → `wait`; reward/risk < 2 → `wait`; never issues `buy_candidate` on incomplete evidence.
  - `scripts/backtest_core.py` — exploratory technical backtest (EMA20/50+RSI14, next-open fill, explicit fees/slippage, 20-session hold, latest-year holdout). Always returns `production_validated=False`; one real run showed an unexplained 164-day source gap → `exploratory_unvalidated`.
- NOT automated (agent-executed per symbol): Codal body entity/units verification, sector context, halt/status per symbol, live order book queues.
- The whole pipeline is a conservative heuristic, NOT a validated profitable system. The backtest result is exploratory only.
- Legacy experiments under `C:/tmp/webmellat_out` are deprecated evidence, not maintained helpers; never execute or reuse their conclusions.
- Lack of source session date is a hard block on current actionable advice. Use `market_core.fetch_market_session()` — it returns the exchange-published date, not a local clock. Per-symbol data whose session ≠ that date must not be presented as current.

## How to Run
Run the bundled `scripts/screener.py` with the available Python through `terminal`:
- `--market-csv <saved CSV> --out <scratch directory>` runs a reproducible first-stage screen.
- `--live --out <scratch directory>` downloads `finpy_tse.Get_MarketWatch(save_excel=False)` (returns market and order-book DataFrames) and screens it.
- The live collector runs in a bounded subprocess (`--timeout 90` seconds by default); a failed run writes `insufficient_data`, exits nonzero and replaces stale result JSON. Use a unique scratch output directory per run to avoid concurrent-run collisions. Input timestamps remain unverified unless separately established.
- This helper produces ONLY a preliminary shortlist and an upper-limit watchlist, never a buy recommendation. Continue the verification below for any shortlisted symbol before promoting it. If only watchlist names remain, report `زیر نظر؛ خرید در سقف فعلاً توصیه نمی‌شود`, not a claim that no demand or opportunity exists. Upper-limit price alone does not establish a queue or inaccessible entry.
- Run `scripts/test_screener.py` (and each `scripts/test_*.py`) after modifying any helper. Test fixtures are synthetic unit tests, never market evidence.
- Scratch evidence from the 2026-10-10 upgrade lives under `C:/Users/hami/AppData/Local/hermes/cache/scratch/tse-upgrade/` (market session JSON, وبملت technical/flow analysis, Codal report selections + interim HTML sample, فولاد backtest run). Scratch entries are pruned after ~24h; re-fetch when stale.

## Procedure
1. **Identify universe and timestamps.** Save raw market snapshot and acquisition timestamp separately from the exchange session date. A library Download timestamp is NOT proof of the data's session. Deduplicate instrument IDs or symbols; record all stage counts in JSON. Restrict to regular ordinary shares in بورس/فرابورس; exclude funds, rights, derivatives, base market, block/bulk transactions, halted/stale instruments. Check metadata rather than trusting name suffix alone. Never exclude a company merely because its name contains صندوق/اوراق or its ticker contains a digit/ends in ح; ordinary issuers such as وصندوق، بورس and انرژی3 can otherwise be lost. Generic CSV metadata are provisional; authoritative identity/status verification remains required. Conflicting duplicates are excluded rather than arbitrarily keeping the last row.
2. **First-stage shortlist.** Require actual trading value, positive price/volume, valid real-person counts/volumes and balanced buy/sell totals. Prioritize liquidity; the helper uses the top quartile of today's value, at least 500 trades, positive EPS, buyer-power >=1.5, positive net individual volume, last >= final, positive daily return and no limit-up chase. These are chosen conservative screening defaults, not laws or attributed trader rules. Save EVERY passing name before ranking; inspect at most five highest-liquidity names initially. Expand only if needed; disclose limited verification coverage.
3. **Historical liquidity and technicals.** Call `analysis_core.analyze_history(raw, adj, price_basis='weighted_final_adjusted')`. It enforces: explicit price basis (ValueError otherwise), ≥250 sessions for EMA200 (else `insufficient_history`), conflicting-date rejection, invalid-OHLC rejection, calendar-gap warning, prior-only volume windows. Parse the returned status before reading indicators. Map pivot levels (already on raw last-trade scale) to current price explicitly.
4. **Tape confirmation.** Call `analysis_core.analyze_flow(ct_df)` after `download_client_types_records` (numeric-coerced internally). It returns dated metrics with mirror-side nets flagged (`nets_are_mirror_sides: true`) — never count corporate and individual net buying as two confirmations. Zero participant counts yield `buyer_power: null`, not a clipped denominator.
5. **Issuer fundamentals.** Call `codal_core.select_reports(symbol, issuer_name)` — it filters letters by exact CompanyName (subsidiaries excluded even when Symbol matches), detects consolidated scope and period from the title, and stops pagination on repeated pages. Download the ExcelUrl and run `codal_core.detect_format(bytes)` — Codal serves HTML with a .xlsx extension; parse with `pandas.read_html` when format is html. Final entity/units verification must read the report body, not the title. If the correct statement cannot be verified, verdict is نامشخص, not a buy.
6. **Conservative final gates.** Assemble a case dict (sessions, per-check evidence with source+date) and call `decision_core.evaluate(case, as_of=today)`. It is fail-closed: any check missing source/date evidence, any session mismatch with the exchange-published reference date, or reward/risk < 2 → verdict `unknown` or `wait`, never buy. A weak general market (from `fetch_market_session()['context']`) warrants waiting. Unknown critical data block buy. No automatic buy from a score or pattern count.
7. **Executable risk plan.** Define observed entry, structural invalidation/stop and first independently observed resistance/target. Reward/risk = (target - entry - estimated round-trip costs per share)/(entry - stop + estimated round-trip costs per share); require target > entry > stop > 0 and ratio >=2 for conservative buy. Use verified fees/slippage or explicit assumptions. NEVER target/stop. Never invent a distant second target to pass the ratio gate. Consider queue, gap and halt risk: stops are not guaranteed execution prices. Do not choose portfolio allocation without knowing portfolio/risk budget.
8. **Report.** Return at most three fully checked opportunities; prefer sector diversity when quality is comparable. State exactly how many names received initial screening versus full verification if coverage matters. In an incomplete trial, return `نامشخص` and blocker, not a buy. No performance promises or probability/win-rate claims without valid out-of-sample evidence.

## Pitfalls
- Quotes at best bid/ask are not necessarily buy/sell queues. Large orders can be cancelled; they are not executed money or definitive pressure.
- Daily aggregate flow cannot establish code-to-code transfers, trader identity/intent, manipulation or intraday tick paths. Require intraday evidence; otherwise say possible, not confirmed.
- Volume spikes and buyer power are clues. A failed filter does not prove no smart money; a passed filter does not prove accumulation.
- Highs can be valid breakouts; lows can be continued deterioration. Do not label upper/lower 30% of an annual range distribution/accumulation by fiat.
- An endpoint failure does not establish permanent retirement. Use bounded requests, status/content-type inspection, one informed retry; stop and disclose unresolved required data.
- 1 trillion rials = 0.1 trillion tomans = 0.1 همت. Codal often reports million rials: convert by 10,000,000 to همت (trillion tomans). Verify units each time.
- Never reuse the earlier Mellat analysis as factual evidence: it mixed a subsidiary's financials, dates, units and raw/adjusted prices. Re-fetch before analyzing any symbol.

## Verification
- Raw snapshots, unique universe/stage counts, shortlist/watchlist and per-stage exclusion symbols persisted as JSON/CSV. Reconcile cumulative stage counts with exclusions programmatically.
- Empty/invalid inputs are `insufficient_data`, not a negative investment signal. Check integer share quantities/counts, count-volume consistency, balanced totals and available OHLC/turnover reconciliation. Reject explicitly non-rial, halted or non-equity metadata; missing metadata remains pending, never verified by default.
- Date and currency validation completed; data gaps distinguished from no candidates.
- Required gates individually evidenced for every buy; otherwise نامشخص/صبر کن.
- Correct risk/reward formula tested; current script test suite passes.
- Skill installation success is not proof of a complete market analysis or investment profitability.
