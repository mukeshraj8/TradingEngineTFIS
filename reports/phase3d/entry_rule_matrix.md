# Phase 3D Milestone 1A Entry Rule Matrix

Status: cross-strategy rule-sheet inventory. Analysis only.

Evidence labels:

- `IMAGE_CONFIRMED`: visible in user-provided rule-sheet images.
- `IMAGE_VERIFICATION_REQUIRED`: visible but not reliably readable enough to
  transcribe as an implementation formula.
- `WORKBOOK_CONFIRMATION_REQUIRED`: must be confirmed from source workbook or
  normalized strategy definition before implementation.
- `IMPLEMENTATION_CONFIRMED`: confirmed by existing TFIS implementation,
  configuration, tests, or Phase 3C evidence.
- `INSUFFICIENT_EVIDENCE`: not enough evidence to design a product-specific
  contract path.

| Strategy group | Product | Status branch | Trade leg | Underlying reference | Contract selection prerequisite | Selected-contract reference | Base entry formula family | ORPT/RC applicability | Effective-entry rule | Downstream risk rule | Evidence status | Unresolved issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stock Option Buying Monthly | Option Buy | Bullish/Bullish Confirmed | Call Buy | Spot Previous 2DHH | Strike range, rounding, min OI, near/next contract | Previous HH/LL of final strike | Selected option reference plus percent of final strike | Not shown | Base unless separate missed-entry evidence exists | Targets/SL use final strike or selected option references; excluded from Entry | `IMAGE_CONFIRMED` | Exact selected-contract reference and percentage require `IMAGE_VERIFICATION_REQUIRED` |
| Stock Option Buying Monthly | Option Buy | Bullish/Bullish Confirmed | Put Buy | Spot Previous 4DLL | Strike range, rounding, min OI, near/next contract | Previous HH/LL of final strike | Selected option reference plus percent of final strike | Not shown | Base unless separate missed-entry evidence exists | Targets/SL excluded from Entry | `IMAGE_CONFIRMED` | Exact formula cells require `IMAGE_VERIFICATION_REQUIRED` |
| Stock Option Buying Monthly | Option Buy | Bearish/Bearish Confirmed | Call Buy | Spot Previous 4DHH | Strike range, rounding, min OI, near/next contract | Previous HH/LL of final strike | Selected option reference plus percent of final strike | Not shown | Base unless separate missed-entry evidence exists | Targets/SL excluded from Entry | `IMAGE_CONFIRMED` | Exact formula cells require `IMAGE_VERIFICATION_REQUIRED` |
| Stock Option Buying Monthly | Option Buy | Bearish/Bearish Confirmed | Put Buy | Spot Previous 2DLL | Strike range, rounding, min OI, near/next contract | Previous HH/LL of final strike | Selected option reference plus percent of final strike | Not shown | Base unless separate missed-entry evidence exists | Targets/SL excluded from Entry | `IMAGE_CONFIRMED` | Exact formula cells require `IMAGE_VERIFICATION_REQUIRED` |
| Stock Option Buying | Option Buy | Bullish/Bearish branches | Call Buy/Put Buy | Spot Previous 2DHH or 2DLL visible in simplified sheet | Strike factor, start/end/last-choice strike, min OI, near/next contract | Previous selected option reference | Selected option reference plus percent of final strike | Not shown | Base unless separate missed-entry evidence exists | Multi-target and stop rows excluded from Entry | `IMAGE_CONFIRMED` | Simplified sheet branch mapping requires workbook confirmation |
| Stock Option Selling | Option Sell | Bullish/Bullish Confirmed | Call Sell | Spot Previous 4DLL | Strike range, rounding, OI, ideal/min premium, near/next contract | Previous 4DLL of final strike visible | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact completed-day semantics require workbook confirmation |
| Stock Option Selling | Option Sell | Bullish/Bullish Confirmed | Put Sell | Spot Previous 2DHH | Strike range, rounding, OI, ideal/min premium, near/next contract | Previous 2DHH of final strike visible | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact completed-day semantics require workbook confirmation |
| Stock Option Selling | Option Sell | Bearish/Bearish Confirmed | Call Sell | Spot Previous 2DLL | Strike range, rounding, OI, ideal/min premium, near/next contract | Previous 2DLL of final strike visible | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact completed-day semantics require workbook confirmation |
| Stock Option Selling | Option Sell | Bearish/Bearish Confirmed | Put Sell | Spot Previous 4DHH | Strike range, rounding, OI, ideal/min premium, near/next contract | Previous 4DHH of final strike visible | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact completed-day semantics require workbook confirmation |
| BankNifty Monthly Option Selling | Option Sell | Bullish/Bearish branches | Call Sell/Put Sell | Spot Previous 3DLL/2DHH/2DLL/3DHH by branch | Strike range, 500-lot OI, ideal/min premium, near/next contract | Previous selected option reference | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact mapping and percentages require workbook confirmation |
| BankNifty Weekly Option Selling | Option Sell | Bullish/Bearish branches | Call Sell/Put Sell | Spot Previous 3DLL/2DHH/2DLL/3DHH by branch | Strike range, 500-lot OI, ideal/min premium, near/next contract | Previous selected option reference | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact mapping and percentages require workbook confirmation |
| Nifty Monthly Option Selling | Option Sell | Bullish/Bearish branches | Call Sell/Put Sell | Spot Previous 3DLL/2DHH/2DLL/3DHH by branch | Strike range, 500-lot OI, ideal/min premium, near/next contract | Previous selected option reference | Selected option reference minus percent | Not shown | Base unless separate missed-entry evidence exists | Target and stop excluded from Entry | `IMAGE_CONFIRMED` | Exact mapping and percentages require workbook confirmation |
| Nifty Weekly Option Selling | Option Sell | Bullish/Bearish branches | Call Sell/Put Sell | Spot Previous 3DLL/2DHH/2DLL/3DHH by branch | Strike range, 500-lot OI, ideal/min premium, near/next contract | Previous selected option reference | Selected option reference minus percent | S23 supported offline; all-strategy applicability not proven | Base or Phase 3C recalculated effective entry | Target and stop excluded from Entry | `IMPLEMENTATION_CONFIRMED` for S23, `IMAGE_CONFIRMED` for sheets | S21 and non-S23 ORPT/RC authority unresolved |
| USDINR Futures | Futures | Bull/Bull CF and Bear/Bear CF | Long/Short | FUT:PRV HH/LL references | Instrument already resolved; no option contract selection | Not applicable | Futures reference plus/minus buffer | Shown | Max for long or Min for short recalculation families visible | SL/TRP, targets, APS excluded from Entry | `IMAGE_CONFIRMED` | Exact buffers and row mappings require image/workbook confirmation |
| BankNifty Futures | Futures | Bull/Bull CF and Bear/Bear CF | Long/Short | FUT:PRV HH/LL references | Instrument already resolved; no option contract selection | Not applicable | Futures reference plus/minus buffer | Shown | Max for long or Min for short recalculation families visible | SL/TRP, targets, APS excluded from Entry | `IMAGE_CONFIRMED` | Exact buffers and row mappings require image/workbook confirmation |
| Stock Option Buying Monthly Rollover | Option Buy Lifecycle | Position state and target-status branch | Rollover order | Rollover-day spot/option references | Exit old contract, select next contract, target-status action matrix | Current market price of final strike | CMP of final strike for rollover entry evidence | Not shown | Lifecycle-authorized new entry, not base Entry authority | Target status and stop rows excluded from Entry | `IMAGE_CONFIRMED` | Rollover ownership and target-status transitions require contract design outside Entry |
| Equity future strategies | Equity | Undefined | Undefined | Equity instrument references | Symbol/security validation | Not applicable unless strategy defines option-like derivative | Undefined | Undefined | Undefined | Undefined | `INSUFFICIENT_EVIDENCE` | Do not invent equity rules |

## Matrix Conclusions

- Option strategies require Contract Selection before Base Entry whenever the
  entry formula references the final strike or selected option contract
  history.
- Futures can calculate Base Entry before Gap/Missed-Entry because the traded
  futures instrument is already resolved.
- Gap/Missed-Entry remains a separate Phase 3C capability. Entry consumes its
  missed/not-missed and recalculation output to finalize Effective Entry.
- Risk and Lifecycle rows in the screenshots are evidence for later phases, not
  ownership for the Entry Engine.
