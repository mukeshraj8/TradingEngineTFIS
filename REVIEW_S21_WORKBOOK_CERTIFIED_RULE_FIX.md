# S21 Workbook-Certified Rule Correction

This patch implements only rules now confirmed by both AB6 OS source evidence
and cross-strategy logic.

## Confirmed correction 1 — expiry search count

S21 `BANKNIFTY_OP_SELL_MT_DIFF_2D_3D` specifies:

    No. of Expiry to Check = 1 Exp

The pure strategy engine and the isolated S21 live selector must therefore
search only the resolved Near monthly expiry. The previous Near+Next fallback
was incorrect for S21.

## Confirmed correction 2 — ORPT missed-entry price field

For both:
- Call Sell Entry
- Put Sell Entry

AB6 OS says:

    Check If 09:24:59 AM LL < <Option> Sell Entry

Therefore both option types use the option LOW. The prior Put implementation
used HIGH and was incorrect.

Strict `<` is preserved. Equality is not classified as missed by this rule.

## Deliberately unchanged

This patch does not change:
- S21 5% monthly strike buffer
- 2.00% Ideal Premium
- 1.50% Minimum Premium
- 500-lot OI rule
- 7.50% entry discount
- Target/SL formulas
- S23 behavior
- broker authority

## RC boundary

The exact S21 09:29:59 recalculation formulas are present in the workbook
source, but the pure replay evidence model does not yet provide 09:29:59 LOW
for every newly eligible RC candidate. This patch therefore leaves numerical
RC fail-closed instead of implementing a formula against incomplete evidence.
