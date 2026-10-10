# Evidence and limits

## Sources actually read in the research
- https://learning.emofid.com/buyer-and-seller-power/ — individual volume/count per-capita ratio; inspect multiple sessions and relative volume, not just one ratio.
- https://learning.emofid.com/how-to-identify-smart-money/ — example screening thresholds (4x prior five-day volume, power >2), and warnings about misleading signals. Educational examples, not validated universal cutoffs.
- https://khobregan-sarmaye.com/fa/article/stock-market-smart-money — multiple alternative volume filters; combine with technical and fundamental context. Do not promote inconsistent prose/code thresholds to laws.
- https://khanesarmaye.com/smart-money/ — discusses queues, price location, market context and fake signals. Claims of certainty, hidden intentions and code-to-code inferred from daily totals are not accepted as established facts.

A search result for an instructor's profile or course is NOT review of their trading record or lessons. No verified performance ranking or consensus of named top Iranian traders was established. Do not attribute forum students' remarks to the teacher. Do not claim video lessons were watched when only a page description was read.

## Interpretation safeguards
- Distinguish observation, hypothesis, and trading decision. Example: buyer power >2 is observed concentration of individual purchases; accumulation is a hypothesis; buying additionally requires an executable risk plan.
- Volume and per-capita ratios are correlated; avoid counting redundant metrics as independent confirmations.
- Require persistence plus price response, appropriate liquidity and market context. Do not force corporate net buying together with individual net buying in the same session: their net volumes sum to zero in a complete matched dataset.
- Use prior-only rolling baselines; adjust for capital changes and reporting gaps. Distinguish current-session snapshots from completed daily history.
- Partial market coverage, failed Codal retrieval or unknown exchange date must remain explicit.

## Rules newly chosen for the conservative screen
Top-quartile daily value, >=500 trades, positive EPS, buyer-power >=1.5, positive real net volume, positive daily change, last >= final and below daily upper limit are screening heuristics only. The shortlist is NOT a signal. Confirm historical liquidity, statements, market/sector, status, multi-session flow and reward/risk >=2 before recommending entry. No backtested profitability is claimed.

## Engineering safeguards
- Avoid broad substring universe filters: an insurance-sector name may contain صندوق, and the stock exchange company's name contains اوراق. Use instrument/market metadata and explicit fund prefixes; retain pending identity verification for generic CSV input.
- Retain strong candidates at the upper price limit in a separate watchlist. Equality with the daily ceiling is not proof of a buy queue; do not chase the price or fabricate executable entry.
- Trace why screening returned zero using cumulative stage counts and excluded symbols. Keep data-quality failures separate from strategy rejections.
- Bound legacy-library downloads in a subprocess because its requests may lack timeouts. Replace old result JSON with explicit failure status after unsuccessful collection.
- First-stage tests and live collection do not test Codal parsing, corporate-action adjustment or final signals; those stages require their own implementations and validation before any end-to-end readiness claim.

## Backtest findings (measured, not hypothetical)
The fixed technical proxy (close > EMA20 > EMA50, RSI 50-65, next-open fill, 20-session max hold, explicit fees) was run on 8 liquid symbols over the latest ~1Y (103 closed trades): strategy avg +3.2% vs buy-and-hold avg +170.9%; beat buy-and-hold on 0/8 symbols; win rate 50.5%. Interpretation: late confirmation entries, cost drag from 103 round trips, and the short holding cap cut winners in a rising market. Per-symbol dispersion was wide (فولاد 83% win rate vs وبصادر 19%), so symbol churn matters as much as the signal. In down-markets the expected benefit is drawdown limitation, not alpha. Quote these numbers when asked whether signals would have been profitable; do not extrapolate them to a rising OR falling market without re-running on that period.

## Future validation before claiming improvement in returns
Use point-in-time universes including delisted/failed symbols; as-published Codal statements; correct action-adjusted series; walk-forward out-of-sample splits; transaction fees, tax, slippage, holidays, trading halts, queues and realistic delayed fills. Compare to an appropriate market benchmark and report turnover, drawdown and sample size. No lookahead from pivot confirmation or daily closing data into same-day entries.

## Hermes implementation reference
https://hermes-agent.nousresearch.com/docs/user-guide/features/skills — on-demand SKILL.md plus supporting scripts/references, managed through skill_manage. Manual trigger does not schedule background monitoring.
