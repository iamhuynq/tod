# Plan: Autonomous Quant Research System

**Version:** 1.2
**Date:** 2026-11-26
**Status:** Implementation specification draft. Becomes binding at the
protocol freeze (section 6.1). Items marked **[CONFIRM]** need owner sign-off.

------------------------------------------------------------------------

## 0. Changes from v1.1

Incorporates the technical review of v1.1 (2026-11-26) plus the decision that
Claude Code performs all implementation.

| Area | v1.1 | v1.2 |
|---|---|---|
| Who builds | One part-time developer | Claude Code builds; owner approves at checkpoints (section 2) |
| Holdout | "Forward holdout" from 2026-06 (already in the past) | Protocol freeze timestamp; exposure declaration; prospective period starts at freeze |
| Holdout guard | Data access layer only | Also enforced against the coding agent (section 2.3) |
| Time semantics | Informal label formula | Canonical UTC convention, latency parameter, delayed-entry sensitivity |
| Cost model | One round-trip number per pair | Per-leg fields, taker-only for candle MVP, versioned |
| Multiple testing | FDR "per scan family" | Pre-registered scan families, global trial ledger, trial budgets |
| DSR | Applied generally | Strategy return series only; event studies use event metrics |
| Event independence | Minimum spacing | Plus cross-asset event clusters and cluster counts |
| Baselines | BTC, basket, random entry | Matched to the research question; unconditional forward return is primary |
| Gates | One minimum-effect gate in the scan | Three separate dimensions: behavioral, economic, executability |
| Risk filters | Tagged only | Evaluated as exposure filters on a long baseline |
| Discovery | Scanner = discovery | Scanner = common evaluation layer; pluggable `ConditionGenerator` with trial budgets |
| Universe | Top 30 | 15 pairs for P1-P4; expand after P4; historical reconstruction audited in P0 |
| Status model | Single lifecycle | Lifecycle status + separate `economic_relevance` and `executability` fields |
| LLM (P6) | Custom adapter | Claude Code itself runs as research assistant through the platform CLI |

------------------------------------------------------------------------

## 1. Vision

Build a research platform that generates candidate market behaviors from crypto
data, evaluates every tested condition under a reproducible statistical
protocol, and separates robust findings from noise.

**MVP question:**

> Can the platform discover candidate behaviors from market data, evaluate every
> tested condition under a reproducible statistical protocol, and distinguish
> robust findings from noise?

Profit on the ~USD 500 account is not a success metric. A clean record of
rejected hypotheses is a successful outcome.

### Guiding principles

1. A pattern found in historical data is only a hypothesis.
2. Every evaluated combination is a registered trial. Trials are never hidden.
3. Holdout data is touched once per candidate, by code, after approval.
4. Statistical evidence, economic relevance and executability are separate.
5. Costs are part of the hypothesis.
6. Deterministic code produces all numbers; language models only assist.
7. Research and paper trading only. Live trading needs a separate review.

------------------------------------------------------------------------

## 2. Development Model

### 2.1 Roles

| Role | Responsibility |
|---|---|
| Owner | Approves this spec, the protocol freeze, phase exits, every holdout run, and any change to the protocol |
| Claude Code | Implements all phases, writes tests, runs verification, reports results with command output |

### 2.2 Working rules for Claude Code

- The repository has a `CLAUDE.md` with: build/test commands, single-test
  command, module map, and the holdout rules from 2.3.
- Each phase starts with a short `plan.md`; implementation starts only after
  the owner approves it.
- A phase is complete only when its exit tests (section 12) are run and their
  output is recorded in `docs/phase-reports/P<n>.md`.
- No change to `protocol/` (frozen protocol files) without owner approval and
  a new protocol version.
- Every research run is executed through the platform CLI so it is recorded in
  the trial ledger. Ad-hoc notebook analysis of development data is allowed
  but must be logged as an exploration session with its trial count.

### 2.3 Holdout guard against the coding agent

The agent that writes the system can leak holdout information just as a human
can (for example by printing statistics while debugging). Controls:

1. **Holdout data is not downloaded until P3 is complete.** P1 downloads only
   the development period. The holdout download is a separate command run by
   the validation module.
2. Holdout partitions are stored under `data/holdout/`, outside the
   development data root.
3. `.claude/settings.json` denies `Read` on `data/holdout/**`; `CLAUDE.md`
   forbids inspecting holdout data or its derived statistics.
4. The only code path that reads holdout data is `validation.final_holdout`,
   which requires an approval token created by the owner per candidate, and
   logs every access to `holdout_access_log`.
5. Holdout outputs are written as pass/fail plus the pre-registered metrics
   only; no exploratory output.

------------------------------------------------------------------------

## 3. Decisions

| # | Item | Decision | Status |
|---|---|---|---|
| 1 | Exchange / market | Binance Spot only; `needs_short` findings kept as knowledge | Decided |
| 2 | Universe for P1-P4 | 15 liquid USDT pairs, point-in-time, >= 180 days since listing; expand to 30, then 50 after P4 runtime is measured. P1-P2 engineering first runs on the 5 always-member pairs (BTC, ETH, BNB, SOL, XRP) | Decided |
| 3 | Stored resolution | 1m candles | Decided |
| 4 | Evaluation horizons | 15m, 1h, 4h; 5m diagnostic only | Decided |
| 5 | aggTrades | Deferred to P4b; BTC, ETH + 3 alts if order-flow generators are added | Decided |
| 6 | Order book | Out of scope | Decided; revisit at kill-criteria review |
| 7 | Storage | Parquet + DuckDB/Polars; SQLite metadata | Decided |
| 8 | Dashboard | Streamlit | Decided |
| 9 | LLM | Post-MVP; Claude Code as assistant (section 13) | Decided |
| 10 | Holdout exposure | No research has been performed on data after 2025-11-30 | **[CONFIRM]** |
| 11 | Protocol freeze | At owner approval of the P0 report | **[CONFIRM]** date |

------------------------------------------------------------------------

## 4. Time Semantics

All timestamps are UTC, stored as integer milliseconds.

| Term | Definition |
|---|---|
| Bar key | Binance kline open time. A 1m bar keyed `T` covers `[T, T+60s)` |
| Bar close time | `T + 60s` |
| Feature availability | A feature computed from bars up to key `T` is available at `T + bar_length` (bar close) |
| Decision time `d` | The availability time of the condition |
| Latency `L` | Configurable; default 1 minute |
| Entry | Open of the first 1m bar with key `>= d + L` (proxy fill, see 5.1) |
| Horizon `h` | Elapsed time from entry. Exit = close of the 1m bar whose close time is `entry_time + h` |
| Missing bars | If the entry or exit bar is missing or its quality day failed, the event is dropped and counted in `dropped_events` |

Labels:

```text
gross_ret = exit_price / entry_price - 1
net_ret   = (exit_price * (1 - exit_cost)) / (entry_price * (1 + entry_cost)) - 1
```

**Sensitivity requirement:** every candidate is re-evaluated with `L` = 1, 2
and 5 minutes. An effect that disappears with a 2-minute delay is flagged
`latency_fragile`.

------------------------------------------------------------------------

## 5. Execution and Cost Model

### 5.1 Execution model (MVP)

- Market (taker) orders only. Limit orders are not modelled, because candle
  data cannot estimate fill probability or adverse selection.
- Fill price = next-bar open (proxy). Reports label it as a proxy, never as a
  realistic fill.
- Order notional: USD 100 (a fraction of the ~USD 500 account). Recorded per
  run.

### 5.2 Cost model fields (versioned in `cost_model`)

| Field | MVP value |
|---|---|
| `entry_fee`, `exit_fee` | 0.10% each (standard taker, no BNB discount assumed) **[CONFIRM]** against current schedule and account tier |
| `entry_spread`, `exit_spread` | Half-spread estimate per pair, from Corwin-Schultz high-low estimator on 1m bars, floored at 0.01% (BTC/ETH) and 0.03% (others) |
| `entry_slippage`, `exit_slippage` | 0.5 x half-spread |
| `order_type` | `market` |
| `order_notional_usd` | 100 |
| `liquidity_context` | Trailing 1h quote volume at decision time; events where notional > 0.1% of that volume are dropped |
| `version`, `source_timestamp`, `assumptions_note` | Required |

Indicative round trip: ~0.22% (majors) to ~0.30% (other pairs). Reports state
that costs are estimates from candle data, not execution-grade.

------------------------------------------------------------------------

## 6. Research Protocol

### 6.1 Data periods and protocol freeze

| Period | Dates | Use |
|---|---|---|
| Development | 2022-01-01 to 2025-11-30 | Discovery, in-sample tests, walk-forward |
| Locked holdout A | 2025-12-01 to 2026-05-31 | One confirmatory test per candidate |
| Locked holdout B | 2026-06-01 to freeze date | Second confirmatory test for candidates that pass A |
| Prospective | Freeze date onward | Paper validation; data that did not exist when the protocol was fixed |

- Holdout A and B are temporal holdouts, not prospective data. They are valid
  only if they have not influenced the protocol (decision 10).
- The freeze writes `protocol/protocol.yaml` with `protocol_version`,
  `freeze_timestamp`, `holdout_policy_version`, period dates, cost model
  version, and statistical parameters. Every candidate stores these.
- Any exposure later discovered is recorded in `holdout_exposure_log`, and the
  affected period is downgraded to development use.

### 6.2 Scan families and the trial ledger

- A **scan family** is declared before execution in a family spec: generator,
  parameter grid, assets, horizons, period, correction method, and type
  (`exploratory` or `confirmatory`).
- Every evaluated combination writes a `trial` row, including those that fail
  any gate. Exploration sessions (2.2) also record their trial counts.
- A **global trial ledger** tracks cumulative trials per generator and in total.
  It feeds DSR and the kill criteria.
- Each generator has a **trial budget** per protocol version (section 7.2).
  Exceeding it requires owner approval.

### 6.3 Statistics by result type

| Result type | Metrics | Significance |
|---|---|---|
| Event study (exploratory) | Event count, independent cluster count, mean / median / quantiles of net return, loss tail (5th percentile), difference vs matched baseline | Block bootstrap CI; Benjamini-Hochberg at q = 0.10 within the family; permutation test across the family for families with strongly correlated trials |
| Confirmatory test (holdout) | Pre-registered metric and threshold only | Pre-registered one-sided test at alpha = 0.05, Holm correction if several metrics |
| Strategy (P7 candidates) | Portfolio return series, Sharpe, max drawdown, turnover | Deflated Sharpe Ratio using the global trial ledger |

DSR is never computed from a pooled set of event returns.

### 6.4 Event independence

- Within a pair: minimum spacing between events >= horizon.
- Across pairs: events whose decision times fall within the same 15-minute
  window **and** coincide with a market shock (BTC or basket move beyond its
  rolling 3-sigma) share an `event_cluster_id`.
- Reports show both asset-event count and independent cluster count. Minimum
  for any exploratory pass: 30 independent clusters.
- Bootstrap resamples contiguous time blocks (block length >= 1 day), not
  individual events.

### 6.5 Baselines

| Question | Baseline |
|---|---|
| Does condition X predict forward returns? | Unconditional forward returns, same pair, horizon and period (primary) |
| Does X matter beyond regime? | Matched events from the same regime label |
| Does a cross-asset event matter? | Same timestamps on comparable pairs not meeting the condition |
| Is the pattern unusual? | Placebo: random entries matching pair, hour-of-day, regime and event count |
| Does a strategy add value? | BTC buy-and-hold, equal-weight universe basket |

### 6.6 Three evaluation dimensions

| Dimension | Question | Gate |
|---|---|---|
| Behavioral | Is there a repeatable difference from the baseline? | Exploratory pass: FDR q <= 0.10, >= 30 clusters, neighbor-threshold robustness |
| Economic | Does it survive the cost model? | Mean net return > 0 with bootstrap lower bound > 0, and gross effect >= 2x round-trip cost |
| Executability | Can Spot express it? | `long_entry`, `risk_filter`, or `needs_short` |

A behavioral pass that fails the economic gate is stored with
`economic_relevance = sub_cost` (subject to a storage budget of 200 records
per protocol version). It is knowledge, not a trading candidate.

### 6.7 Robustness scope

Each hypothesis declares its scope: `market_wide`, `group` (named group) or
`pair_specific`.

| Scope | Requirement |
|---|---|
| market_wide | >= 10 eligible pairs and effect sign consistent in >= 60% of them |
| group | >= 5 eligible pairs in the group and >= 60% consistent |
| pair_specific | Passes on its own pair; stricter FDR (q = 0.05) because it is easier to overfit |

Reports include eligible count, passing count, median effect and dispersion.

### 6.8 Risk filter evaluation

A `risk_filter` is evaluated as a modification of a long baseline (always-long
equal-weight basket, and always-long single pair):

- return and max drawdown with vs without the filter;
- upside missed during filtered periods;
- added turnover and costs from exiting and re-entering;
- results per regime.

It passes economically only if drawdown falls and net return after added costs
does not fall by more than the drawdown improvement justifies (pre-registered
ratio, default: return-to-max-drawdown improves).

### 6.9 Kill criteria

Reviewed after P4 plus 4 weeks of scheduled scanning:

- Zero candidates pass holdout A net of costs, **or**
- the global ledger exceeds 100,000 trials with no holdout pass.

Then the owner chooses: longer horizons (4h-1d), add futures for
`needs_short`, add order-flow data, or stop and keep the knowledge base.

------------------------------------------------------------------------

## 7. Discovery

### 7.1 Scanner as the common evaluation layer

The forward-return scanner does not define what can be found. It evaluates
whatever conditions generators produce, under section 6. Generators define the
search space; the scanner and validation make it statistically controlled.

### 7.2 ConditionGenerator interface

```python
class ConditionGenerator(Protocol):
    name: str
    version: str
    data_requirements: list[str]     # e.g. ["klines_1m"], ["agg_trades"]
    trial_budget: int                # max trials per protocol version

    def generate(self, ctx: GenerationContext) -> Iterable[ConditionDefinition]: ...
```

A `ConditionDefinition` is serializable (generator, parameters, assets,
formula), produces a deterministic event list from a data snapshot, and has a
fingerprint used for deduplication.

### 7.3 Generator rollout

| Order | Generator | Phase | Initial budget |
|---|---|---|---|
| 1 | Single-feature thresholds (quantile grid) | P4 | 5,000 |
| 2 | Regime labels and change points (HMM, CUSUM) | P4 | 2,000 |
| 3 | Cross-asset: BTC shock response, relative strength, lead-lag | P4 | 5,000 |
| 4 | Two-feature interactions (only features with a behavioral pass) | P4b | 10,000 |
| 5 | Temporal motifs (Matrix Profile) | P4b | 3,000 |
| 6 | Cluster membership and transitions | P4b | 2,000 |
| 7 | Rule candidates from shallow trees | P4b | 5,000 |

A generator is added only after the previous one passes the synthetic tests in
section 12 (P3 exit). Budgets are owner-adjustable.

------------------------------------------------------------------------

## 8. Data

### 8.1 Sources

| Data | Source |
|---|---|
| Historical 1m klines | `data.binance.vision` monthly / daily archives with `.CHECKSUM` files |
| Exchange metadata (current) | Binance REST `exchangeInfo`, snapshot daily from P1 |
| Live 1m klines (prospective) | Binance REST polling + WebSocket, from P1 |
| aggTrades | `data.binance.vision`, P4b only |

### 8.2 Point-in-time universe and P0 audit

Historical listing status cannot be read from today's `exchangeInfo`. P0 runs
an audit that, for every month from 2022-01:

- lists all USDT symbols present in the archive (including delisted);
- infers listing and delisting from first and last archive dates;
- records trailing 30-day quote volume, ranking timestamp and selected
  universe;
- records missing metadata and a `reconstruction_confidence` (high / medium /
  low).

Excluded: stablecoin-to-stablecoin pairs, leveraged tokens, pegged-price
pairs, pairs with less than 180 days of history at ranking time (post-listing
behavior is atypical). Months with low confidence are marked
incomplete and excluded from market-wide claims, never silently filled with
today's symbols.

### 8.3 Data-quality checks

Per `(pair, date)`:

- archive checksum verified;
- gaps, duplicate keys and non-monotonic keys;
- zero-volume or OHLC-inconsistent bars;
- symbol renames / migrations mapped in `symbol_alias`;
- UTC consistency (no local-time conversions anywhere);
- backfill log with source URL, checksum, download time.

Status: `pass`, `warn`, `fail`. Experiments exclude `fail` days. A
`data_snapshot` references both the partitions and their quality report.

### 8.4 Volume

15 pairs x 1m x 4 years ~ 32M rows (< 1 GB Parquet). 50 pairs ~ 105M rows.
Local disk is sufficient.

------------------------------------------------------------------------

## 9. Architecture

```text
src/qrs/
  data/          ingestion, quality, universe, snapshots, holdout guard
  features/      feature definitions, labels, cost model
  conditions/    ConditionGenerator implementations
  research/      scanner, scan families, trial ledger, hypotheses, experiments
  validation/    statistics, baselines, walk-forward, final_holdout
  reporting/     result records, reports
  dashboard/     Streamlit app
  cli/           single entry point: qrs <command>
protocol/        frozen protocol files (owner approval to change)
data/dev/        development Parquet
data/holdout/    holdout Parquet (P3+, agent read-denied)
data/live/       prospective Parquet
docs/            plans, phase reports
tests/
```

| Layer | Choice |
|---|---|
| Language | Python 3.12, `uv` for environments |
| Processing | Polars, DuckDB, NumPy |
| Statistics | SciPy, statsmodels, `arch` (bootstrap) |
| ML | scikit-learn, hmmlearn, stumpy (P4b) |
| Metadata | SQLite via SQLAlchemy (PostgreSQL later if needed) |
| Scheduling | cron calling `qrs` commands |
| Quality | pytest, ruff, mypy |
| Reproducibility | Every run stores git commit, snapshot ID, protocol version, params, seed |

------------------------------------------------------------------------

## 10. Data Model (metadata)

| Entity | Purpose |
|---|---|
| `pair`, `symbol_alias`, `universe_membership` | Symbols and point-in-time universe with confidence |
| `data_snapshot` | Partitions + quality report reference |
| `cost_model` | Per-leg cost fields, versioned |
| `feature_definition`, `condition_definition` | Versioned formulas, fingerprints |
| `scan_family` | Pre-declared family spec |
| `trial` | One evaluated combination |
| `exploration_session` | Ad-hoc analysis with trial count |
| `discovery` | Trials that passed the behavioral gate |
| `hypothesis` | Statement, scope, executability, alternatives, pre-registered test |
| `experiment`, `experiment_run` | Spec and executions |
| `validation_result` | Walk-forward, robustness, latency, holdout outcomes |
| `holdout_access_log`, `holdout_exposure_log` | Holdout governance |
| `protocol_version` | Frozen protocol references |

------------------------------------------------------------------------

## 11. Status Model

Three independent fields per hypothesis, never merged into one score.

**`lifecycle_status`**

```text
OBSERVED -> EXPLORATORY_PASS -> HYPOTHESIS -> DEVELOPMENT_VALIDATED
  -> HOLDOUT_PENDING -> HOLDOUT_PASS -> PAPER_TRADING -> DECAYED / RETIRED
Any step -> REJECTED (reason required)
```

A candidate that fails a holdout is `REJECTED` and cannot be re-tested on that
holdout. New evidence must come from a later period.

**`economic_relevance`**: `unknown`, `sub_cost`, `survives_costs`

**`executability`**: `long_entry`, `risk_filter`, `needs_short`

Only `HOLDOUT_PASS` + `survives_costs` + (`long_entry` or `risk_filter`) can
enter `PAPER_TRADING`.

### Result record

```json
{
  "discovery_id": "DISC-000001",
  "condition_definition_id": "COND-000001",
  "generator": "single_threshold@1.0",
  "scan_family_id": "FAMILY-000001",
  "data_snapshot_id": "SNAP-000001",
  "code_commit": "git-sha",
  "protocol_version": "1.2",
  "cost_model_version": "COST-000001",
  "scope": "market_wide",
  "assets": ["BTCUSDT", "ETHUSDT"],
  "horizon": "1h",
  "latency_minutes": 1,
  "event_count": 0,
  "independent_cluster_count": 0,
  "mean_net_return": null,
  "median_net_return": null,
  "p05_net_return": null,
  "ci_95": null,
  "baseline": "unconditional",
  "baseline_difference": null,
  "q_value": null,
  "lifecycle_status": "OBSERVED",
  "economic_relevance": "unknown",
  "executability": "risk_filter",
  "flags": []
}
```

Schema illustration only, not a real result.

------------------------------------------------------------------------

## 12. Roadmap

Claude Code implements every phase. Wall-clock time is driven mainly by owner
review, data downloads and compute, so phases are sized by scope and gated by
exit tests rather than week estimates.

| Phase | Scope | Exit tests (run by Claude Code, reviewed by owner) | Size |
|---|---|---|---|
| **P0 Spec + audit** | Repo scaffold, `CLAUDE.md`, holdout guard settings, archive coverage audit, universe reconstruction audit, fee confirmation, protocol draft | Audit report per month; protocol draft approved; **protocol freeze** | S |
| **P1 Data** | Download development period for 15-pair universe; checksums; quality checks; snapshots; daily exchangeInfo + live kline collector | Quality report per pair-day; snapshot reproducible by ID; live collector 7 days with no unexplained gaps | M |
| **P2 Features + labels + costs** | 20-30 features with availability rules; labels per section 4; cost model v1 | Look-ahead test: shifting future data does not change any feature; labels match hand-computed samples; latency variants computed | M |
| **P3 Validation** | Trial ledger, scan families, bootstrap, FDR, permutation test, event clusters, baselines, walk-forward, holdout download + guard | Null test: on shuffled labels, false discovery rate <= q; injected test: a planted effect of known size is recovered; guard test: any non-validation read of holdout fails | L |
| **P4 Scanner baseline** | Scanner + generators 1-3, discovery registry, dedup | Full scan reproducible from IDs; trial ledger complete (count equals grid size); runtime measured for 15 and 30 pairs | M |
| **P5 Dashboard** | Streamlit: families, trials, discoveries, hypotheses, holdout log | Every displayed result links to commit + snapshot + protocol | S |
| **P4b Discovery expansion** | Generators 4-7, optional aggTrades | Each generator passes null and injected tests before use | L |
| **P6 Research assistant** | Section 13 | Assistant proposals go through family specs and budgets; no holdout access in tests | S |
| **P7 Paper trading** | Eligible candidates only; simulated taker fills on live data; drift monitoring | >= 3 months of prospective results compared with pre-registered expectations | Runs >= 3 months |

**MVP = P0 to P5.** Owner checkpoints: P0 freeze, end of each phase, every
holdout run, kill-criteria review.

------------------------------------------------------------------------

## 13. Research Assistant (P6)

Instead of building a custom LLM agent, P6 uses Claude Code (headless or
scheduled) as the research assistant, operating only through the `qrs` CLI.

**Allowed commands:** read discovery and result summaries, write a family spec
proposal, write a hypothesis draft (alternatives, confounders, test plan),
generate research summaries.

**Not allowed:** changing statuses, running holdout validation, editing
`protocol/`, reading `data/holdout/`, exceeding trial budgets.

Family specs proposed by the assistant run only after owner approval, or
automatically if they use an approved template and fit the remaining budget.
All prompts, outputs and commands are logged to `agent_run`.

------------------------------------------------------------------------

## 14. Risks

| Risk | Mitigation |
|---|---|
| Data snooping across repeated scans | Global trial ledger, budgets, pre-declared families, confirmatory holdouts |
| Coding agent leaks holdout information | Holdout not downloaded before P3; read-deny; approval token; access log |
| Look-ahead | Section 4 semantics; automated look-ahead test |
| Inflated sample size | Event clusters; block bootstrap; cluster-count minimum |
| Survivorship | Archive-based universe with confidence; low-confidence months excluded |
| Costs exceed effects | Conservative taker model; economic gate; longer horizons |
| Latency-fragile effects | Delayed-entry sensitivity, `latency_fragile` flag |
| Agent-written statistics bugs | Null and injected-effect tests at P3 exit; owner review |
| Scope creep | Generator rollout order, budgets, phase exit tests |
| Regime change | Prospective period, DECAYED status, periodic re-validation |

------------------------------------------------------------------------

## 15. Open Items

| # | Item | Needed by |
|---|---|---|
| 1 | Confirm no research has used data after 2025-11-30 (decision 10) | P0 |
| 2 | Confirm fee tier and whether BNB discount applies | P0 |
| 3 | Approve protocol freeze date | End of P0 |
| 4 | Approve generator trial budgets | Before P4 |
