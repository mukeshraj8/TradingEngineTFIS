# S21 User Decision Pack

Verdict: `S21_USER_DECISION_PACK_CLOSED`

Scope: S21 BankNifty monthly option-selling source questions only. This pack
does not implement S21 and does not change runtime, configuration, broker,
paper, live, workbook, source, script, or test behavior.

Closure status as of 2026-08-02:

- `S21-Q001`: closed by source-closure directive using Option 1.
- `S21-Q002`: closed by source-closure directive using Option 1.
- `S21-Q003`: closed by authoritative APS clarification as
  `APS_NOT_APPLICABLE`.
- `S21-Q004`: closed by authoritative one-lot Option Selling quantity
  clarification.
- `S21-Q005`: closed by source-closure directive using Option 1.

No financially material S21 source questions remain open. The original
question analysis below is retained as the audit trail.

Primary workbook:

- `TFISRulesAndSpec/All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`
- SHA-256:
  `603ea7bc09ebb0c7df2ad0202d492c9ca49e890cfefdb3f0eddb1edcbe8fbddd`

Additional authoritative source:

- `TFISRulesAndSpec/TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`

## Monthly Status Architecture Confirmation

Monthly Status is calculated by the generic, strategy-independent Monthly
Status Engine. It accepts structured eligible instruments, evaluation
date/timestamp, monthly candle/reference evidence, Monthly Status rule version,
and provenance/data quality. It returns immutable instrument-specific Monthly
Status results with source monthly references, transition/continuation
evidence, evaluation timestamp, data-quality state, warnings/failures, and a
deterministic result hash.

S21 consumes BANKNIFTY Monthly Status. S21 branch mapping is separate from the
generic Monthly Status calculation. No S21 formula belongs inside the Monthly
Status engine. Future S22 stock instances must request independent Monthly
Status results per enabled F&O stock.

Source separation:

- Generic Monthly Status calculation: Monthly Status v1.0 specification.
- S21 Monthly-Status-to-branch mapping: `AB6 OS!D100:D110`,
  `AB6 OS!F100:F110`, `AB6 OS!J100:K110`.
- S21 cached consumed status: `AB11!D11 = Bull CF`.

## S21-Q001 Contract / Expiry Fallback

Business stage: contract selection and expiry selection.

Why the answer is required: the selected expiry determines the tradable
contract, premium, OI qualification, entry, target, SL, and carried-position
expiry risk.

Authoritative workbook evidence:

- `AB2!V26 = Monthly : NEAR`
- `AB2!W26 = Every Week On Wed (TD)`
- `AB2!X26 = EXP Day - 0 TRD Day`
- `AB2!Y26 = 14:20:00`
- `AB1!D28 = BANKNIFTY`
- `AB1!F28 = Monthly : NEAR`
- `AB1!I28 = EXP Day - 0 TRD Day`
- `AB1!K28 = EXP Day - 2 TRD Day`
- `AB11!E11 = Monthly : NEAR`
- `AB11!G11 = 2024-01-25`
- `AB11!J11 = 2024-02-29`
- `AB15!J11 = L/CE : Exp : Near _ S/PE : Exp : Next`
- `AB15!K11 = BANKNIFTY 25-Jan-2024 CE 47000`
- `AB15!L11 = 2024-01-25`
- `AB15!N11 = BANKNIFTY 29-Feb-2024 PE 48000`
- `AB15!O11 = 2024-02-29`
- `AB6 OS!I101/I104/I107/I110 = 1 Exp`
- `AB6 OS!I100/I103/I106/I109 = 500 Lots`

Adjacent interpretation context:

- `AB6 OS!G100:G110` defines Call/Put branch-specific strike ranges.
- `AB6 OS!H100:H110` defines ideal/minimum premium thresholds.
- `AB6 OS!I100:I110` shows minimum OI and `1 Exp` labels.
- `AB15!J11:P11` shows a cached final CE Near and PE Next result.

Workbook-supported interpretations:

1. Independent near-first fallback: search Near expiry first for each option
   type; if the selected option type has no qualifying contract in Near, search
   Next. This is supported by `Monthly : NEAR`, `1 Exp`, and the cached
   `CE Near / PE Next` result.
2. Fixed CE Near and PE Next: Call side always uses Near and Put side always
   uses Next for this S21 setup. This is supported only by the cached
   `AB15!J11:P11` row, not by an explicit rule statement.
3. Same-expiry requirement: both Call and Put must use the same expiry. This is
   weakly suggested by `AB16!E80 = SAME`, but contradicted by cached
   `AB15!J11:P11` showing CE Near and PE Next.
4. Near-only: `Monthly : NEAR` and `1 Exp` could mean search only Near. This is
   contradicted by cached PE Next output.

Recommended interpretation: Option 1, independent near-first fallback, but only
with user approval.

Why recommended: it aligns with the existing monthly-status driven strategy
contract, explains why CE selected Near while PE selected Next in the cached
row, and avoids forcing both legs into one expiry when the workbook output
already differs.

Proposed executable sequence requiring approval:

1. Resolve Near and Next monthly expiries from instrument metadata.
2. For the active Call or Put branch, search Near expiry across the workbook
   strike range.
3. Qualify by OI threshold.
4. Prefer first qualifying strike satisfying ideal premium.
5. If no ideal-premium strike qualifies in Near, search Near minimum-premium
   candidates.
6. If Near has no qualifying strike, insufficient OI, premium outside ideal
   range, or premium below minimum, search Next expiry using the same phases.
7. If Next also has no qualifying contract, return `NO_TRADE`.
8. Do not require Call and Put to use the same expiry unless user explicitly
   confirms that rule.
9. Tie-breaking remains unresolved unless user confirms directional traversal
   from start strike to end strike as the tie-break.

Consequences:

- Option 1: may select CE and PE independently; most consistent with cached
  output; requires auditable per-leg expiry evidence.
- Option 2: simpler but could force PE to Next even when Near qualifies.
- Option 3: may reject or distort a leg when the other leg has selected a
  different expiry.
- Option 4: could block trades where Next should be used.

Call/Put difference: yes, workbook cached output differs: CE Near, PE Next.

Rule category: strategy-specific contract-selection policy plus generic
contract-selection engine behavior. Near/Next calendar identity is instrument
metadata behavior.

Other sheet evidence: no sheet found with a full executable Near/Next fallback
sequence. `AB15` appears to contain final cached output, not general rule
authority.

Existing configuration match: existing S21 config/scaffold appears to support
monthly expiry metadata and fallback-style fields, but the config cannot become
authority until this question is answered.

Legacy comparison: not performed as authority. Legacy S21 may differ, but must
be inspected only after source closure as discrepancy evidence.

Exact user response format:

```text
S21-Q001: Option 1
Clarification: For S21, search Near monthly expiry first independently for each
Call/Put leg. If no qualifying contract is found due to strike, OI, ideal
premium, or minimum premium failure, search Next monthly expiry. If Next also
fails, do not trade that leg. Call and Put do not need the same expiry.
Tie-break: traverse from Start Strike to End Strike and choose the first
qualifying strike.
```

## S21-Q002 Gap Classification

Business stage: generic opening gap classification, S21 ORPT missed-entry, and
S21 RC recalculation.

Why the answer is required: the platform must know whether S21 has a separate
GAP_UP/GAP_DOWN/no-gap business decision or whether the workbook's `Gap Check`
only means ORPT entry-missed detection.

Authoritative workbook evidence:

- `AB6 OS!D112 = Gap Check`
- `AB6 OS!E112 = Process`
- `AB6 OS!M112 = Rules For Gap = Step 1 Start Strike`
- `AB6 OS!O112 = Rules For Gap = Step 2 End Strike`
- `AB6 OS!X112 = Rules For Gap = Step 3 Revised Option Entry`
- `AB6 OS!E113 = Check If 09:24:59 AM LL < Call Sell Entry`
- `AB6 OS!G113 = No`
- `AB6 OS!H113 = Entry Not Missed`
- `AB6 OS!I113 = Place the Order at ORPT`
- `AB6 OS!L113 = 09:24:59.400000`
- `AB6 OS!G114 = Yes`
- `AB6 OS!H114 = Entry Missed`
- `AB6 OS!I114 = Recalcuate : Call Sell Entry : Bull / Bull CF`
- `AB6 OS!L114 = 09:29:59.400000`
- `AB6 OS!E116 = Check If 09:24:59 AM LL < Put Sell Entry`
- `AB6 OS!G116 = No`
- `AB6 OS!H116 = Entry Not Missed`
- `AB6 OS!I116 = Place the Order at ORPT`
- `AB6 OS!G117 = Yes`
- `AB6 OS!H117 = Entry Missed`
- `AB6 OS!I117 = Recalcuate : Put Sell Entry : Bull / Bull CF`
- `AB6 OS!I118 = Recalcuate : Put Sell Entry : Bear / Bear CF`

Adjacent interpretation context:

- The workbook labels the section `Gap Check`, but the executable comparisons
  are ORPT low against entry.
- No explicit S21 gap reference, opening price/reference, gap-up operator,
  gap-down operator, buffer, or no-gap state was found.

Workbook-supported interpretations:

1. `NOT_APPLICABLE_TO_S21_BRANCH_LOGIC`: generic OpeningMarketContext may
   record gap facts, but S21 branch behavior consumes only ORPT missed-entry
   and RC recalculation evidence.
2. S21 has an implied gap classifier hidden behind `Rules For Gap` labels, but
   the actual operator and reference cells are missing from the inspected
   source.
3. Gap Check and Missed Entry are the same workbook concept for S21.

Recommended interpretation: Option 1.

Why recommended: it avoids inventing gap-up/gap-down formulas that do not
appear in the S21 workbook cells, while preserving generic OpeningMarketContext
gap observation for audit.

Consequences:

- Option 1: S21 remains source-faithful; generic gap evidence is auditable but
  does not create S21-specific action.
- Option 2: blocks implementation until a separate gap formula source is
  supplied.
- Option 3: may be acceptable only if the user confirms that S21's workbook
  label `Gap Check` means missed-entry detection.

Call/Put difference: the ORPT missed-entry operator is parallel for Call and
Put (`09:24:59 AM LL < Entry`), but RC formulas differ by branch/option type.

Rule category: generic platform behavior for opening gap observation; S21
strategy-specific behavior for ORPT missed-entry and RC formulas.

Other sheet evidence: no other inspected S21 workbook sheet contains a
separate GAP_UP/GAP_DOWN/no-gap authority.

Existing configuration match: existing gap/missed-entry compatibility has
historically treated S21 timing/gap behavior as unresolved or evidence-only;
it should not be treated as authority.

Legacy comparison: not authoritative. Existing legacy-adjacent code mentions
S21 unresolved timing profiles, consistent with blocking source closure rather
than implementing a separate S21 gap formula.

Exact user response format:

```text
S21-Q002: Option 1
Clarification: S21 has no separate GAP_UP/GAP_DOWN/no-gap branch logic for V1.
Generic OpeningMarketContext may record opening gap evidence, but S21 trade
behavior uses only the workbook ORPT missed-entry checks and RC recalculation
rules.
```

## S21-Q003 APS / Partial Exits

Business stage: APS, partial exits, target quantities, remaining quantities,
and Target/SL linkage after APS.

Why the answer is required: APS can change exit quantity, target behavior,
remaining position size, and protection requirements. Implementing it from the
label alone could exit too much, too little, or leave a position unprotected.

Authoritative workbook evidence:

- `AB2!K26 = APS`
- `AB6 OS!C107 = APS`
- `AB15!S11 = APS`
- `AB16!E79 = APS`
- `AB16!M75/M82 = TGT Lots ( Qty )`
- `AB16!N75/N82 = 0`
- `AB16!K75/K82 = 1`
- `AB16!M78/M85 = SL Lots ( Qty )`
- `AB16!N78/N85 = 1`
- `AB16!P78:P85`, `Q78:Q85`, `R78:R85`, `S78:S85`, `T78:T85` show repeated
  SL quantity columns with `1`.
- `AB16!Q83:U84` formulas suppress later targets when `E79 = APS`.
- `AB18!O37/O40 = 0` for target output quantities.
- `AB18!O38/O41 = 15` for stop-loss output quantities.

Adjacent interpretation context:

- AB16 formula cells indicate APS affects target-column availability, but the
  inspected source does not define APS as an executable order, timing, trigger,
  repeatability, or protection-resize process.
- AB18 target rows exist but have zero target quantity in the cached S21 output.
- AB18 stop-loss rows have quantity 15 in the cached S21 output.

Workbook-supported interpretations:

1. APS is a workbook target-profile label that suppresses ordinary target
   orders for this S21 cached case; target quantity is zero and SL protects the
   full quantity.
2. APS means an additional profit-stop/trailing process, but the trigger and
   formula are not in the inspected cells.
3. APS means partial square-off or target allocation, but target quantities are
   zero in the cached AB18 output.
4. APS is output/report metadata only for S21 V1.

Final interpretation: APS is not applicable to S21 Option Selling because the
configured trading quantity is one lot.

Why final: the authoritative 2026-08-02 user clarification states that APS is
not applicable to one-lot Option Selling strategies such as S21, S22 and S23.

Consequences:

- APS is `NOT_APPLICABLE`: S21 uses one complete position with one Target and
  one protection sequence.
- Do not create partial Target allocation, quantity splitting, partial
  PositionCycle, or APS-specific protection adjustment for S21.

Call/Put difference: unknown from source. Cached Call and Put both show APS and
zero target output quantity, but this does not prove all branches match.

Rule category: strategy-specific unless later proven to be a global Option
Selling APS process.

Other sheet evidence: AB16 formulas contain APS handling logic, but no complete
business rule for activation/timing/quantity/protection behavior was found.

Existing configuration match: current S21 scaffolding may contain APS labels or
target-profile fields, but that does not supply executable authority.

Legacy comparison: not authoritative and not performed for closure.

Closed user response:

```text
S21-Q003: USER_CLARIFIED
Clarification: APS is NOT_APPLICABLE to S21 execution because S21 is one-lot
Option Selling. Use only verified Target/SL/FSL/TRP/EOD/carry-forward behavior;
do not create partial-exit or APS orders unless a future source explicitly
defines them for a multi-lot strategy.
```

## S21-Q004 Quantity And P&L Unit

Business stage: quantity, lot handling, and accounting/P&L unit.

Why the answer is required: wrong lot/exchange-unit conversion can double-count
or under-count orders and P&L.

Authoritative workbook evidence:

- `AB11!H11 = 15`
- `AB11!K11 = 15`
- `AB11!V11 = 100`
- `AB11!X11 = 100`
- `AB15!U11 = 2`
- `AB16!K75 = 1`
- `AB16!K82 = 1`
- `AB16!I77 = 15`
- `AB16!I84 = 15`
- `AB16!W77/W84 = Lot ( Qty )`
- `AB16!Y77/Y84 = 0`
- `AB16!Z77/Z84 = 15`
- `AB18!O37/O40 = 0`
- `AB18!O38/O41 = 15`
- `AB6 OS!I100/I103/I106/I109 = 500 Lots`
- `AB16!AK79 = Min OI`
- `AB16!AL79 = 7500`

Adjacent interpretation context:

- `500 Lots` appears in OI filter cells and maps to `7500` when lot size is 15.
- Cached execution output quantities are 15 for stop-loss rows, consistent
  with one lot of lot size 15.
- `AB15!U11 = 2` is not normalized by the available source and may not be
  execution quantity.

Workbook-supported interpretations:

1. Trading quantity is one lot; lot size is 15; exchange quantity is 15;
   P&L multiplier is exchange quantity; `500 Lots` is an OI threshold;
   `AB15!U11 = 2` is non-execution metadata.
2. `AB15!U11 = 2` means configured quantity is two lots, but this conflicts
   with AB16 one-lot and AB18 quantity-15 output.
3. `500 Lots` is order quantity. This is contradicted by AB16/AB18 quantities
   and by `Min OI = 7500`.

Recommended interpretation: Option 1, but only with user approval because
quantity is financially material.

Why recommended: it is the only interpretation consistent with AB16 one lot,
AB16 lot size 15, AB18 stop-loss quantity 15, and the OI conversion 500 lots *
15 = 7500.

Consequences:

- Option 1: avoids double multiplication; orders use 15 exchange units for one
  lot; P&L uses confirmed exchange quantity.
- Option 2: could place or account for 30 units if interpreted as two lots.
- Option 3: would be an extreme over-order if 500 lots were treated as trade
  quantity.

Call/Put difference: cached Call and Put quantities match, but future branch
differences should remain data-driven.

Rule category: instrument metadata behavior plus strategy/account sizing
policy plus generic accounting behavior.

Other sheet evidence: no additional inspected sheet explains `AB15!U11 = 2`.

Existing configuration match: existing S21 config/scaffold may contain lot size
and quantity fields, but must be checked against the approved quantity
semantics before implementation.

Legacy comparison: not authoritative and not performed for closure.

Implementation metadata that must be retained after approval:

- `quantity_lots`
- `lot_size`
- `quantity_exchange_units`
- `lot_size_effective_date`
- metadata source

Exact user response format:

```text
S21-Q004: Option 1
Clarification: For S21, configured trading quantity is 1 lot. BANKNIFTY lot
size is 15 per workbook source, so exchange quantity is 15. P&L must multiply
by confirmed exchange quantity, not by lot size again. "500 Lots" is minimum
OI threshold, not order quantity. AB15!U11=2 is not execution/P&L quantity for
S21 V1.
Lot size effective date/source: ...
```

## S21-Q005 Rollover / Expiry Action

Business stage: rollover/expiry for carried positions.

Why the answer is required: rollover and expiry handling determine whether an
open position is exited, carried, rolled into another contract, or blocked for
manual review.

Authoritative workbook evidence:

- `AB2!X26 = EXP Day - 0 TRD Day`
- `AB2!Y26 = 14:20:00`
- `AB2!Z26 = EXP Day - 1 TRD Day`
- `AB2!AA26 = EXP Day - 1 TRD Day`
- `AB11!M11 = EXP Day - 0 TRD Day`
- `AB11!N11 = 14:20:00`
- `AB11!P11 = EXP Day - 1 TRD Day`
- `AB1!I28 = EXP Day - 0 TRD Day`
- `AB1!K28 = EXP Day - 2 TRD Day`
- `AB6 OS!J97/U97 = Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules`
- `AB6 OS!A121:Z126` contains next-day carried/open-position FSL/TRP rules.

Adjacent interpretation context:

- Near/Next expiry fallback for fresh contract selection does not prove
  rollover behavior for an already open position.
- EOD carry-forward is verified for Option Selling when close is less than or
  equal to Original SL.
- Open-position next-day SL/FSL/TRP behavior is defined, but automatic close
  and reopen into Next expiry is not found.

Workbook-supported interpretations:

1. No automatic rollover: fresh entries use contract-selection rules; existing
   open positions follow EOD/carry and carried-position lifecycle; unsupported
   expiry continuation fails closed.
2. Close old and open new on a rollover date. Expiry metadata suggests dates,
   but no complete open-position close/reopen action text was found.
3. Carry same contract through expiry-day lifecycle until verified EOD/expiry
   rule acts. This may be unsafe without an explicit expiry continuation rule.
4. Select Next only for fresh entries, not carried positions.

Recommended interpretation: Option 1, requiring user approval.

Why recommended: it avoids inferring rollover from fresh-entry Near/Next
selection, preserves verified EOD/carry and carried lifecycle rules, and fails
closed before unsupported expiry continuation.

Consequences:

- Option 1: safest; may require manual/operator decision on unsupported expiry
  continuation.
- Option 2: could create unauthorized new exposure and realized P&L events.
- Option 3: could carry an option too close to or through expiry without
  authority.
- Option 4: acceptable if paired with explicit no-automatic-rollover and
  fail-closed expiry governance.

Call/Put difference: possible, because cached selected expiries differ by
option type.

Rule category: strategy-specific lifecycle policy plus future generic
lifecycle capability. It is not generic contract-selection behavior by itself.

Other sheet evidence: no inspected sheet contains a complete open-position
rollover action rule.

Existing configuration match: existing expiry metadata cannot authorize
automatic rollover.

Legacy comparison: not authoritative and not performed for closure.

Exact user response format:

```text
S21-Q005: Option 1
Clarification: S21 has no automatic rollover for open positions in V1. Fresh
entries follow approved contract-selection rules. Open positions follow
verified EOD/carry and carried-position lifecycle rules. If a position would
continue into an unsupported expiry state, fail closed and require operator/user
decision; do not close old and open new automatically.
```
