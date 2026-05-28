# S23 FYERS Ingress Live Runbook

## Purpose

This runbook defines the first safe local procedure for running S23 against
real FYERS market data in ingress-only paper mode.

Scope:

- S23 only
- NIFTY only
- weekly options only
- paper mode only
- broker market-data only
- no fills
- no lifecycle
- no broker order placement
- no real-money execution

## Required Environment

Required environment variables for real FYERS data:

- `FYERS_APP_ID`
- `FYERS_ACCESS_TOKEN`

Optional:

- `FYERS_CLIENT_ID`

If `broker.payload_fixture_path` is present in the config, the runner stays in
fixture mode and preflight returns `WARNING` instead of a live-data `PASS`.

Recommended local PowerShell setup before a real run:

```powershell
$env:FYERS_APP_ID = "<your-app-id>"
$env:FYERS_ACCESS_TOKEN = "<your-access-token>"
$env:FYERS_CLIENT_ID = "<optional-client-id>"
```

## Required Config

Primary config:

- `config/paper.s23.yaml`

Mandatory safety fields:

- `broker.provider: fyers`
- `paper.strategy_code: S23`
- `paper.symbol: NIFTY`
- `paper.contract_cycle: WEEKLY`
- `paper.mode: paper`
- `paper.paper_mode_enabled: true`
- `paper.same_day_square_off_only: true` for the current same-day ingress-only rollout
- `paper.kill_switch_enabled: true`
- `paper.session_kill_switch_active: false`
- `paper.no_live_orders_allowed: true`
- `paper.allow_recalculation: false` for the first real ingress-only run
- `source_mode: broker_fyers_live_paper_ingress`

Mandatory market fields:

- `market.underlying_symbol: NIFTY`
- `market.weekly_expiry`
- `market.selected_contract_symbol` only when intentionally using a deterministic smoke override

## Prelude JSONL Role

The broker layer must not own S23 logic.

The prelude JSONL supplies the non-broker planning context:

- `CALENDAR_CONTEXT`
- `MONTHLY_STATUS_INPUT`
- `UNDERLYING_SNAPSHOT` for required labels:
  - `0915`
  - `ORPT`
  - `RC` when current-day `FSL / TRP` is enabled
- `TRADE_PLAN_INPUT`

TFIS can now build this paper prelude from normalized runtime inputs through
the paper-only prelude builder under `src/tfis/paper/live_prelude.py`.

Current limitation:

- FYERS socket and live-session orchestration still do not build or manage this
  prelude automatically
- the existing live ingress runner still expects supplied prelude events
- static `market.selected_contract_symbol` remains a smoke-test override only

The FYERS adapter supplies only broker market-data events:

- `UNDERLYING_QUOTE`
- `OPTION_CHAIN_SNAPSHOT`
- `SELECTED_CONTRACT_QUOTE`
- optional `SELECTED_CONTRACT_BAR`

## Market-Hours Requirement

Real FYERS ingress-only runs should be performed on an active market day during
live market hours.

Recommended window:

- start preflight before market open or before the intended decision window
- run ingress during the live S23 decision window

Preflight itself does not connect and can be run safely outside market hours.

## Symbols To Subscribe

The runner subscribes to:

- underlying: `NIFTY`
- selected contract: `market.selected_contract_symbol` in the current ingress-only smoke path

Operational note:

- runtime contract selection should come from normalized option-chain records
- static `market.selected_contract_symbol` should remain a smoke-test override, not the main operational path
- OI must be present for selected-contract candidates; missing OI is a hard selection failure

The FYERS adapter converts the normalized TFIS option symbol into FYERS format
internally. S23 still consumes only normalized TFIS events.

## Market-Data Requirements

Underlying quote requirements:

- usable NIFTY quote must be available
- quote timestamps must be timezone-aligned
- stale underlying data is a close-out blocker

Option-chain requirements:

- option chain must be available at decision time
- expiry must match the configured weekly expiry
- missing chain at decision time is `NO_GO`

Selected-contract quote requirements:

- selected contract must be available
- selected contract freshness must stay within the configured quote-age limit
- missing selected contract is `NO_GO`

## Checklist Before Any Real Run

- market is open and this is an active trading day
- `broker.payload_fixture_path` is removed or commented out
- `FYERS_APP_ID` and `FYERS_ACCESS_TOKEN` are present in the shell
- prelude JSONL was generated for today
- `paper.strategy_code` is still `S23`
- `paper.mode` is still `paper`
- `paper.no_live_orders_allowed` is still `true`
- `paper.session_kill_switch_active` is still `false`
- artifact root path is writable

## Preflight Command

Safe local preflight:

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-preflight-live `
  --preflight-only `
  --out-json tmp/s23_fyers_paper_ingress/preflight.json `
  --out-md tmp/s23_fyers_paper_ingress/preflight.md
```

What preflight checks:

- config is present and parseable
- FYERS credentials exist when fixture mode is off
- order placement is blocked
- paper mode is enabled
- strategy is S23
- symbol is NIFTY
- contract cycle is weekly
- same-day-only policy is enabled
- session kill switch is not already active
- selected contract symbol is configured
- required prelude events and snapshots exist
- source mode is still ingress-only
- artifact root is writable
- broker timezone is valid
- for a real run, prelude session date matches the local broker date
- fill simulation is disabled
- lifecycle simulation is disabled

What preflight does not do:

- it does not connect to FYERS
- it does not place orders
- it does not simulate fills
- it does not run lifecycle monitoring

## Fixture-Backed Smoke Test

Use this before the first real run to verify the local command path:

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-fixture-smoke `
  --out-json tmp/s23_fyers_paper_ingress/fixture_smoke.json `
  --out-md tmp/s23_fyers_paper_ingress/fixture_smoke.md
```

Expected result:

- fixture-backed `WARNING` is acceptable for preflight
- ingress run reaches `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED`
- no order, fill, or lifecycle artifacts are produced

## Real Ingress-Only Command

After preflight passes and fixture mode is removed:

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl <today-normalized-prelude.jsonl> `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-live-ingress
```

This path must remain ingress-only:

- no fills
- no lifecycle
- no broker order placement

## Output Checklist

Required session artifacts for the first real run:

- `broker_health.json`
- `normalized_events.jsonl`
- `ingress_summary.json`
- `selected_contract_audit.json`
- `paper_session_review.md`
- `no_trade_or_order_plan_summary.json`

Required reused paper-shell artifacts:

- `session_manifest.json`
- `decision_summary.json`
- `audit_events.jsonl`

Must not exist for the first ingress-only run:

- `paper_fill.json`
- `paper_no_fill.json`
- `paper_position.json`
- `paper_exit.json`
- `paper_pnl_summary.json`
- `lifecycle_events.jsonl`
- any broker order artifact

## Expected Output Artifacts

From the broker-backed ingress runner:

- `broker_health.json`
- `normalized_events.jsonl`
- `ingress_summary.json`
- `selected_contract_audit.json`
- `paper_session_review.md`
- `no_trade_or_order_plan_summary.json`

From the reused paper shell:

- `session_manifest.json`
- `decision_summary.json`
- `audit_events.jsonl`
- `paper_order_plan.json` when planned
- `no_trade_summary.json` or `abort_summary.json`

## PASS / WARNING / NO_GO Criteria

### Preflight PASS

- real FYERS credentials present
- no payload fixture mode
- all mandatory safety flags valid
- required prelude events and snapshots present
- selected contract configured
- artifact root writable
- valid broker timezone
- prelude session date matches the local broker date
- ingress-only mode confirmed
- fill and lifecycle remain disabled

### Preflight WARNING

- payload fixture mode is still enabled

- or this is an intentional local smoke-test rehearsal rather than a real run

Warnings require operator review before treating the run as live-like.

### Preflight NO_GO

- missing FYERS credentials for live mode
- order placement is not blocked
- paper mode is disabled
- non-S23 strategy
- non-NIFTY symbol
- non-weekly contract cycle
- non-paper mode
- session kill switch already active
- selected contract missing
- required snapshots missing
- invalid prelude event types
- invalid timezone
- artifact root not writable
- real-run session date mismatch
- any non-ingress-only source mode

## Runtime Close-Out Criteria

Use `docs/operations/s23_operator_closeout_policy.md` after the actual ingress
run.

Current ingress-only thresholds:

- `PASS`
  - zero stale events
  - zero late events
  - zero missing chains
  - zero missing selected contracts
  - zero timezone mismatches
  - `ORPT` / `RC` lag `<= 2.5s`
  - no fill or lifecycle artifacts created
- `WARNING`
  - hard safety checks still pass
  - `ORPT` / `RC` lag `> 2.5s` and `<= 5.0s`
- `NO_GO`
  - timezone mismatch
  - requested multi-session continuation in the current same-day runtime
  - chain missing at decision time
  - selected contract missing
  - stale market data
  - `ORPT` / `RC` lag `> 5.0s`
  - any fill or lifecycle artifact exists

## Manual Review Required

Manual review is required when:

- preflight returns `WARNING`
- ingress close-out returns `WARNING`
- selected-contract freshness is close to threshold
- the session ends in `NO_TRADE` or `ABORTED`
- `current_day_fsl_trp` overlays are involved

## Hard Safety Rule

Do not modify this runner to place orders.

The allowed architecture remains:

`Broker Adapter -> Normalized Market Event Layer -> TFIS Paper Engine`

S23 must never consume raw FYERS payloads directly, and this runner must remain
market-data only until a separate order-routing design is approved.
