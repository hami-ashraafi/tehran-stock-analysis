---
name: tehran-stock-analysis
description: Use for TSE analysis or «فرصت خرید پیدا کن» screening.
version: 2.5.0
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

## Market regime gate (buy_gate)

New buys are only allowed when the official TSE **equal-weighted index (شاخص هموزن)** closes above its own EMA50. Use `scripts/regime_gate.py` → `market_regime()` → `buy_gate_open`. Rationale: the cap-weighted شاخص کل is dominated by a few giants; هموزن reflects the average tradeable stock. When `buy_gate_open` is false, screening may still run for watchlist purposes but every verdict must be `wait`, never بخر. The gate uses the index's own session date, not the local clock. The pytse index key is `شاخص كل` spelled with Arabic ك — passing the Persian ک spelling raises KeyError; copy the key exactly or reuse `regime_gate.INDEX_NAME`.

`analyze_history` lowercases dataframe columns internally before use — pass the download output directly and never index `adjClose` (camelCase) yourself; the provider's column case varies across symbols and versions and a hand-rolled rename will crash with KeyError.

## Momentum-chase guard (hard no-buy)

A candidate meeting ALL of: RSI14 > 80, price up >100% over ~3 months, and daily gains pinned near the daily limit for a week or more → verdict صبر کن regardless of flow strength. Strong net-individual inflows during a parabolic run are late-chaser evidence, not accumulation evidence; early holders are exiting into that demand. Entry consideration only after a pullback to the rising EMA20/first pivot support with renewed demand. Additionally: if no own-issuer interim statement can be verified on Codal for the symbol, the fundamental check is نامشخص — flow alone never substitutes for it.

## Codal robustness (silent failures)
`codal_core._get_json` swallows HTTP/JSON errors and returns None, and `search_letters`/`select_reports` can silently return 0 letters / `interim: None` — an empty result is NOT evidence that no statement exists. On empty/None: retry, and if wrappers still return nothing, call the `SEARCH_URL` directly with plain `requests` (params `Page`, `PageSize`, `Symbol=<url-encoded ticker>`), then filter `CompanyName.strip() == issuer_name` client-side and dedupe by `TracingNo`. A Symbol query returns the parent AND its subsidiaries; subsidiary letters carry `(شرکت ...) ` in the title — exclude those to find the issuer's own letters. If the parent has no own interim letter at all, fundamental check stays نامشخص (per momentum-chase guard) — do not substitute a subsidiary's financials.

## Sector diagnosis (چرا گروه X ...؟)

For 'why is sector X red/green today': pull `finpy_tse.Get_MarketWatch(save_excel=False)`, filter `Sector.str.contains('<sector keyword>')`, report red/green counts, median `Close(%)`, aggregate net individual volume (`Vol_Buy_R - Vol_Sell_R`) and group value. Then `web_search` the sector name + today's Persian date for catalysts. Attribute causes as محتمل (probable) unless an official/regulator source confirms — news searches during/after hours often return stale or unrelated articles, and matching the sector's pattern to a macro driver (e.g. currency moves for banks) is hypothesis, not fact.

## Pre-breakout funnel (multi-stage screening, validated 2026-10-20)

Single-day strict screening fails the real question: it surfaces limit-locked leaders (Close == Day_UL, 29/30 in one run) or one near-ceiling name — exactly what the user rejects («چیزی بخر که داره میره تو سود، نه رسیده به سقف»). When the user wants executable short-term entries, run this funnel AFTER (or instead of) stage 1:

1. **Relaxed pre-screen** on the live market frame: `locked = Close == Day_UL`; require unlocked with `room_pct = (Day_UL-Close)/Close > 0.5%`, Value > 200B rial, EPS > 0, net individual volume (Vol_Buy_R - Vol_Sell_R) > 0, `Close(%) > -0.5`. Keep ~20 candidates; save to candidates.csv.
2. **Multi-timeframe momentum** via `finpy_tse.Get_Price_History(recent_days=…, start Jalali, end Jalali)` — Jalali dates REQUIRED (Gregorian silently returns an empty DataFrame). Compute per symbol: 5d/20d price change, close vs EMA10, vol_ratio (5d vol / 20d avg).
3. **Flow** via `pytse_client.download_client_types_records(symbols=list, include_jdate=True)` — columns are ENGLISH (`individual_buy_vol`, `individual_sell_vol`, …), not Persian; a Persian-column matcher yields zero rows for every symbol (empty ≠ no flow). Compute net_ind 5d (M shares), buyer power 5d, per-capita buy volume.
4. **Composite score** (18-point): above EMA10 +2; chg_5d>2% +2, 0–2% +1; chg_20d>10% +2; vol_ratio≥1 +2; net_ind_5d>50M shares +3; bp_5d>1.5 +2; per-capita>10K +2; room_pct>1.5% +2; EPS>0 +1; **penalty −3 when chg_20d>80% (overextended/late-chase)**. Rank and report top names with all metrics, flagging near-ceiling names (room <1%) as queue-risk even when scores are high.
5. Interpretation archetypes: strong momentum + rising volume + inflow + room = «در حال رفتن به سود»; positive 20d trend + today's pullback + high per-capita buy = dip-buy candidate (unconfirmed reversal — flag it); huge 20d gain (>80%) = late stage, distribution risk.

The strict single-day screener stays the conservative default for the standard «فرصت خرید پیدا کن» contract; this funnel is for the explicit «قابل خرید، داره میره تو سود» short-term request.

## Pre-breakout funnel (multi-stage screening, validated 2026-10-20)

Single-day strict screening fails the real question: it surfaces limit-locked leaders (Close == Day_UL, 29/30 in one run) or one near-ceiling name — exactly what the user rejects («چیزی بخر که داره میره تو سود، نه رسیده به سقف»). When the user wants executable short-term entries, run this funnel AFTER (or instead of) stage 1:

1. **Relaxed pre-screen** on the live market frame: `locked = Close == Day_UL`; require unlocked with `room_pct = (Day_UL-Close)/Close > 0.5%`, Value > 200B rial, EPS > 0, net individual volume (Vol_Buy_R - Vol_Sell_R) > 0, `Close(%) > -0.5`. Keep ~20 candidates; save to candidates.csv.
2. **Multi-timeframe momentum** via `finpy_tse.Get_Price_History(start Jalali, end Jalali)` — Jalali dates REQUIRED (Gregorian silently returns an empty DataFrame). Compute per symbol: 5d/20d price change, close vs EMA10, vol_ratio (5d vol / 20d avg).
3. **Flow** via `pytse_client.download_client_types_records(symbols=list, include_jdate=True)` — columns are ENGLISH (`individual_buy_vol`, `individual_sell_vol`, …), not Persian; a Persian-column matcher yields zero rows for every symbol (empty ≠ no flow). Compute net_ind 5d (M shares), buyer power 5d, per-capita buy volume.
4. **Composite score** (18-point): above EMA10 +2; chg_5d>2% +2, 0–2% +1; chg_20d>10% +2; vol_ratio≥1 +2; net_ind_5d>50M shares +3; bp_5d>1.5 +2; per-capita>10K +2; room_pct>1.5% +2; EPS>0 +1; **penalty −3 when chg_20d>80% (overextended/late-chase)**. Rank and report top names with all metrics, flagging near-ceiling names (room <1%) as queue-risk even when scores are high.
5. Interpretation archetypes: strong momentum + rising volume + inflow + room = «در حال رفتن به سود»; positive 20d trend + today's pullback + high per-capita buy = dip-buy candidate (unconfirmed reversal — flag it); huge 20d gain (>80%) = late stage, distribution risk.

The strict single-day screener stays the conservative default for the standard «فرصت خرید پیدا کن» contract; this funnel is for the explicit «قابل خرید، داره میره تو سود» short-term request.

## Evidence-based exit policy (from variant experiments, 2026-10-10)

Backtested on 8 liquid symbols, ~2y window, with fees/slippage. The original default (20-session cap + signal-loss exit) yielded median +4.3% vs buy&hold +79%, beating B&H on 0/8 symbols. Conclusions, ranked by evidence strength:

1. **Drop the 20-session holding cap** for trend entries; it exits winners early. Keeping EMA100 as the exit anchor instead: median return rose from +4.3% to +35.4% with drawdown still ~-26% (vs B&H drawdown ~-50/60%).
2. **Regime anchor matters more than entry tweaks**: exiting only when close < EMA100 (or EMA200) captured multi-month trends (فملی +206%, فخوز +112%, شپنا +192%). Wider RSI entry bands (45-70) added ~+3pp median but raised DD; weak evidence, optional.
3. **Never trade the slow variant (EMA20>50 + RSI band) without a regime exit** — full-history test (17y): median -86% from overtrading whipsaws with fee drag. Short-term EMA crossover entries are destructively active on TSE; if used at all, combine with EMA100/200 exit and expect ~8-10 trades/2y, not 190+.
4. **None of the tested variants beat buy-and-hold on return** in this 2-year sample (rising market). Their value is drawdown control: strategy DD ~-26% vs B&H ~-50/64%. Present them as loss-limiting overlays, not alpha.
5. **Multiple-comparisons discipline** (Bailey & López de Prado, DSR): we tested 11 variants across 2 windows; a best-of-11 winner is partly luck. Track the trial count with every experiment; do not claim an edge without out-of-sample confirmation, and prefer median across symbols over the single best case.

Operational rule going forward: recommend the EMA100-exit overlay (entry unchanged: close>EMA20>EMA50, RSI 50-65; exit: close<EMA100 next-open) as the conservative default; keep the 20-session cap only when the user explicitly asks for short holding periods.

## Implemented scope and limitations
- Executable modules (all tested, 74 synthetic unit tests):
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
- The live collector runs in a bounded subprocess (`--timeout 90` seconds by default); a failed run writes `insufficient_data`, exits nonzero and replaces stale result JSON. Use a unique scratch output directory per run to avoid concurrent-run collisions. Import `screener` with the working directory set to `scripts/` (or `sys.path.insert(0,'scripts')`) — importing from the skill root raises ModuleNotFoundError. Input timestamps remain unverified unless separately established.
- This helper produces ONLY a preliminary shortlist and an upper-limit watchlist, never a buy recommendation. Continue the verification below for any shortlisted symbol before promoting it. If only watchlist names remain, report `زیر نظر؛ خرید در سقف فعلاً توصیه نمی‌شود`, not a claim that no demand or opportunity exists. Upper-limit price alone does not establish a queue or inaccessible entry.
- Executable-entry gate (short-term buy requests): compute `locked = (Close == Day_UL)` per candidate from the market frame and the remaining gap to `Day_UL`. Names at the limit are قفل خرید — report them as locked, never as actionable buy signals, and do not assign them targets/stops. For a user asking «قابل خرید باشه», present ONLY unlocked names, or an unlocked near-limit name explicitly flagged with queue risk. A shortlist full of locked names is reported as «سیگنال هست ولی قابل خرید نیست» plus any single unlocked candidate, not converted into buy advice. (and each `scripts/test_*.py`) after modifying any helper. Test fixtures are synthetic unit tests, never market evidence.
- Scratch evidence from the 2026-10-10 upgrade lives under `C:/Users/hami/AppData/Local/hermes/cache/scratch/tse-upgrade/` (market session JSON, وبملت technical/flow analysis, Codal report selections + interim HTML sample, فولاد backtest run). Scratch entries are pruned after ~24h; re-fetch when stale.

## Procedure
1. **Identify universe and timestamps.** Save raw market snapshot and acquisition timestamp separately from the exchange session date. A library Download timestamp is NOT proof of the data's session. Deduplicate instrument IDs or symbols; record all stage counts in JSON. Restrict to regular ordinary shares in بورس/فرابورس; exclude funds, rights, derivatives, base market, block/bulk transactions, halted/stale instruments. Check metadata rather than trusting name suffix alone. Never exclude a company merely because its name contains صندوق/اوراق or its ticker contains a digit/ends in ح; ordinary issuers such as وصندوق، بورس and انرژی3 can otherwise be lost. Generic CSV metadata are provisional; authoritative identity/status verification remains required. Conflicting duplicates are excluded rather than arbitrarily keeping the last row.
2. **First-stage shortlist.** Require actual trading value, positive price/volume, valid real-person counts/volumes and balanced buy/sell totals. Prioritize liquidity; the helper uses the top quartile of today's value, at least 500 trades, positive EPS, buyer-power >=1.5, positive net individual volume, last >= final, positive daily return and no limit-up chase. These are chosen conservative screening defaults, not laws or attributed trader rules. Save EVERY passing name before ranking; inspect at most five highest-liquidity names initially. Expand only if needed; disclose limited verification coverage.
3. **Historical liquidity and technicals.** Call `analysis_core.analyze_history(raw, adj, price_basis='weighted_final_adjusted')`. It enforces: explicit price basis (ValueError otherwise), ≥250 sessions for EMA200 (else `insufficient_history`), conflicting-date rejection, invalid-OHLC rejection, calendar-gap warning, prior-only volume windows. Parse the returned status before reading indicators. Map pivot levels (already on raw last-trade scale) to current price explicitly.
4. **Tape confirmation.** Call `analysis_core.analyze_flow(ct_df)` after `download_client_types_records` (numeric-coerced internally). It returns dated metrics with mirror-side nets flagged (`nets_are_mirror_sides: true`) — never count corporate and individual net buying as two confirmations. Zero participant counts yield `buyer_power: null`, not a clipped denominator.
5. **Issuer fundamentals.** First establish current-price context via `t.Ticker(symbol).instrument_id` (insCode) → `https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/<insCode>` and `.../api/ClosingPrice/GetClosingPriceInfo/<insCode>` (JSON; gives staticThreshold bounds, 52w min/max, estimated EPS, sector PE, live pClosing vs yesterday) — plain `requests` works; `t.Ticker` convenience getters (get_eps_value etc.) do not. The `BestLimits` endpoint returns an error-JSON shape, do not rely on it.
`finpy_tse` has NO `Get_Client_Type_History` — use `pytse_client.download_client_types_records` (English columns; see pre-breakout funnel). Passing a bare module to pytse `download*` raises 'module object is not subscriptable' — always pass a list of symbols and index the returned dict by ticker.
Then call `codal_core.select_reports(symbol, issuer_name)` — it filters letters by exact CompanyName (subsidiaries excluded even when Symbol matches), detects consolidated scope and period from the title, and stops pagination on repeated pages. If it returns empty/None, fall back to the direct-requests recipe in «Codal robustness» above. Download the ExcelUrl and run `codal_core.detect_format(bytes)` — Codal serves HTML with a .xlsx extension; parse with `pandas.read_html` when format is html. Final entity/units verification must read the report body, not the title. If the correct statement cannot be verified, verdict is نامشخص, not a buy.
6. **Conservative final gates.** Assemble a case dict (sessions, per-check evidence with source+date) and call `decision_core.evaluate(case, as_of=today)`. It is fail-closed: any check missing source/date evidence, any session mismatch with the exchange-published reference date, or reward/risk < 2 → verdict `unknown` or `wait`, never buy. A weak general market (from `fetch_market_session()['context']`) warrants waiting. Unknown critical data block buy. No automatic buy from a score or pattern count.
7. **Executable risk plan.** First, when the user states available capital, size every recommendation against it: default risk cap 10% of capital per position, and state the max share count executable without material impact given the symbol's average daily value. Verify the current کد به کد disclosure threshold before claiming an order is below it — do not state that threshold from memory. Then define observed entry, structural invalidation/stop and first independently observed resistance/target. Reward/risk = (target - entry - estimated round-trip costs per share)/(entry - stop + estimated round-trip costs per share); require target > entry > stop > 0 and ratio >=2 for conservative buy. Use verified fees/slippage or explicit assumptions. NEVER target/stop. Never invent a distant second target to pass the ratio gate. Consider queue, gap and halt risk: stops are not guaranteed execution prices. Do not choose portfolio allocation without knowing portfolio/risk budget.
8. **Report.** Return at most three fully checked opportunities; prefer sector diversity when quality is comparable. State exactly how many names received initial screening versus full verification if coverage matters. In an incomplete trial, return `نامشخص` and blocker, not a buy. No performance promises or probability/win-rate claims without valid out-of-sample evidence.

## Pitfalls
- Quotes at best bid/ask are not necessarily buy/sell queues. Large orders can be cancelled; they are not executed money or definitive pressure.
- Daily aggregate flow cannot establish code-to-code transfers, trader identity/intent, manipulation or intraday tick paths. Require intraday evidence; otherwise say possible, not confirmed.
- Volume spikes and buyer power are clues. A failed filter does not prove no smart money; a passed filter does not prove accumulation.
- Highs can be valid breakouts; lows can be continued deterioration. Do not label upper/lower 30% of an annual range distribution/accumulation by fiat.
- An endpoint failure does not establish permanent retirement. Use bounded requests, status/content-type inspection, one informed retry; stop and disclose unresolved required data.
- 1 trillion rials = 0.1 trillion tomans = 0.1 همت. Codal often reports million rials: convert by 10,000,000 to همت (trillion tomans). Verify units each time.
- Never reuse the earlier Mellat analysis as factual evidence: it mixed a subsidiary's financials, dates, units and raw/adjusted prices. Re-fetch before analyzing any symbol.

## Backtest evidence (do not oversell)
A real run of the technical proxy on 8 liquid symbols (latest ~1Y each, 103 closed trades) returned: strategy avg +3.2% vs buy-and-hold avg +170.9%; strategy beat buy-and-hold on 0/8 symbols; overall win rate 50.5%. Wins concentrated in already-trending names (فولاد 83% win rate) while churn-heavy names lost (وبصادر 19% win rate, -31.6%). When the user asks "would listening to the signals have made money": run `backtest_core.run_backtest` per symbol with `download(..., adjust=True)`, report strategy vs same-symbol buy-and-hold side by side, and state plainly that in rising markets this signal class underperforms severely — its value is loss-limiting (lower drawdowns), not profit generation. Never present the signal engine as a profit engine.

## Verification
- Raw snapshots, unique universe/stage counts, shortlist/watchlist and per-stage exclusion symbols persisted as JSON/CSV. Reconcile cumulative stage counts with exclusions programmatically.
- Empty/invalid inputs are `insufficient_data`, not a negative investment signal. Check integer share quantities/counts, count-volume consistency, balanced totals and available OHLC/turnover reconciliation. Reject explicitly non-rial, halted or non-equity metadata; missing metadata remains pending, never verified by default.
- Date and currency validation completed; data gaps distinguished from no candidates.
- Required gates individually evidenced for every buy; otherwise نامشخص/صبر کن.
- Correct risk/reward formula tested; current script test suite passes.
- This skill ships as a GitHub repo: https://github.com/hami-ashraafi/tehran-stock-analysis (branch `main`). After substantial module changes, commit and push from the skill directory so the repo matches the installed skill; pull before editing if another session may have pushed.
- Skill installation success is not proof of a complete market analysis or investment profitability.
