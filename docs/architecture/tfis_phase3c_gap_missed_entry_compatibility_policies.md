# TFIS Phase 3C Gap/Missed-Entry Compatibility Policies

Status: Milestone 3 compatibility adapter implementation. Offline-only; no
paper, live, replay, or backtest runtime path is activated.

## Implemented Profiles

Compatibility policies live under `src/tfis/adapters/legacy_policies/` and
execute through the generic `GapMissedEntryEngine` contract:

- `legacy.s21.gap_missed_entry.evidence_only_v1`
- `legacy.s21.gap_missed_entry.unresolved_timing_v1`
- `legacy.s23.gap_missed_entry.backtest_low_v1`
- `legacy.s23.gap_missed_entry.paper_live_high_v1`
- `legacy.s23.gap_missed_entry.unresolved_put_v1`

The generic domain package does not import these policies.

## S21 Support

S21 is represented only to the extent supported by current evidence. The
evidence-only profile declares ORPT/RC as `NOT_APPLICABLE` and returns no gap or
missed-entry recalculation behavior. The unresolved timing profile carries
`S21_ORPT_RC_APPLICABILITY_UNRESOLVED`, classifies the issue as
`INSUFFICIENT_EVIDENCE` / `USER_CLARIFICATION_REQUIRED`, and fails closed.

No S21 gap-up/gap-down formula is declared confirmed.

## S23 Branch Mapping

The S23 compatibility adapter supports:

- Bull Call: `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Bear Call: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL`
- Bull Put: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT`
- Bear Put: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`

ORPT and RC are required for executable S23 profiles. Current-day high/low are
carried as gap context. The adapter preserves normal/not-missed, missed,
recalculation-required, completed compatibility recalculation, invalid, and
missing-evidence outcomes separately.

## PUT Profile Handling

The observed PUT inconsistency remains unresolved:

- backtest-low profile compares `OPTION_LOW < entry_price`
- paper/live-high profile compares `OPTION_HIGH < entry_price`

The generic engine never chooses between these profiles. Composition or explicit
test input selects the profile. The unresolved executable profile fails closed
and records both competing observed behaviors.

No workbook rule is declared confirmed.

## Recalculation Outputs

S23 missed-entry recalculation delegates to the existing pure
`S23RecalculationEngine`. The compatibility result may carry:

- recalculated start strike
- recalculated end strike
- recalculated ideal premium
- recalculated minimum premium
- recalculated entry price
- source rule and audit notes

Target, FSL, TRP, MSL, TSL, APS, contract selection, order placement, and
position lifecycle are excluded.

## Composition

`config/strategy_policy_composition.yaml` adds `gap_missed_entry_policy` under
the identity composition records:

- `S21_BANKNIFTY_OP_SELL_MONTHLY@1.0.0`
- `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D@1.0.0`

Resolution requires `strategy_definition_id + strategy_version`. Family-only
resolution and unsupported versions are rejected. Unresolved executable S23 PUT
composition is rejected at config-load time.

## Fail-Closed Cases

Milestone 3 returns structured failures for missing required ORPT/RC,
invalid chronology, missing option observation, UNKNOWN Monthly Status,
unsupported branch, missing base entry/reference, recalculation input gaps, and
unresolved executable PUT profile.

## Adapter-Level Parity

Focused tests prove:

- the backtest-low profile matches `S23EntryMissedDetector`
- S23 recalculation compatibility outputs match `S23RecalculationEngine`
- the two PUT profiles can produce different outputs on the same candle
- evidence records selected profile, observed field, operator, observed value,
  reference value, and recalculation output

Milestone 4 remains responsible for full parity reports and decision-packet
report integration.

## Open Issues Before Milestone 4

- Confirm authoritative S23 PUT missed-entry behavior from workbook/user
  evidence.
- Verify S21 ORPT/RC applicability before any executable S21 gap/missed-entry
  profile is used.
- Map compatibility results into full `TFISDecisionEvidencePacket` reports.
- Keep runtime activation behind a separate reviewed milestone.
