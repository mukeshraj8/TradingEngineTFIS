# TFIS Phase 3C Open Rule Register

Status: Phase 3C certification register. These items remain unresolved after
offline Gap/Missed-Entry certification and must fail closed where executable
behavior would otherwise be inferred.

## TFIS-GME-OPEN-001: S23 PUT Missed-Entry Authoritative Comparison

- affected strategy/version/branch: `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D@1.0.0`,
  Bull Put and Bear Put
- competing evidence: backtest behavior compares `OPTION_LOW < entry`; paper/
  live timing-audit behavior compares `OPTION_HIGH < entry`
- status: `LEGACY_INCONSISTENCY`, `WORKBOOK_VERIFICATION_REQUIRED`,
  `USER_CLARIFICATION_REQUIRED`
- business impact: the same PUT candle can be `MISSED` under the low profile
  and `NOT_MISSED` under the high profile
- current safe behavior: explicit low/high compatibility profiles can be used
  offline; the unresolved PUT profile fails closed
- required resolution source: workbook verification or explicit user rule
  decision
- blocks offline use: no, when a profile is explicitly selected for fixture or
  compatibility parity
- blocks runtime shadow: yes
- blocks live money: yes

## TFIS-GME-OPEN-002: S21 ORPT/RC Applicability

- affected strategy/version/branch: `S21_BANKNIFTY_OP_SELL_MONTHLY@1.0.0`,
  all S21 gap/missed-entry branches
- competing evidence: the evidence-only profile declares ORPT/RC not
  applicable; unresolved applicability fails closed
- status: `INSUFFICIENT_EVIDENCE`, `USER_CLARIFICATION_REQUIRED`
- business impact: TFIS must not infer S23 timing semantics or invent a gap
  formula for S21
- current safe behavior: S21 may emit evidence-only `NOT_APPLICABLE`; unresolved
  timing execution fails closed
- required resolution source: workbook verification or explicit user rule
  decision
- blocks offline use: no, for evidence-only certification
- blocks runtime shadow: yes
- blocks live money: yes

## TFIS-GME-OPEN-003: Full Captured Parity Availability

- affected strategy/version/branch: S21/S23 captured runtime evidence for every
  profile intended for runtime migration
- competing evidence: Milestone 4 has one partial captured parity case; the
  remaining cases use synthetic golden evidence or deterministic legacy
  fixtures
- status: evidence/capture gap, not a formula-rule defect
- business impact: supported offline parity is certified, but complete
  runtime-shadow confidence is not yet established
- current safe behavior: runtime shadow remains deferred unless adequate
  captured evidence exists or explicitly approved supplemental evidence is used
- required resolution source: captured option-chain/timing evidence or an
  approved supplemental evidence plan
- blocks offline use: no
- blocks runtime shadow: yes
- blocks live money: yes
