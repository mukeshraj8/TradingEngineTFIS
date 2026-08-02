# S22 Source Completeness Checklist

Verdict: `S22_SOURCE_AND_UNIVERSE_CONDITIONAL`

S22 workbook business rules are source-traced. Universe and instrument-metadata
governance is architecture-ready. Implementation is blocked only until the
first explicit operator-enabled stock is supplied.

| Capability | Status | Authority |
| --- | --- | --- |
| Strategy identity | VERIFIED | `AB2!A27:AH27`, `AB6 OS!A131:C138` |
| One common multi-stock definition | VERIFIED | `AB2!D27:E27`, `AB10!E12`; AGENTS multi-instrument invariant |
| Monthly Status consumption | VERIFIED | `AB11!D12`; generic Monthly Status invariant |
| Branch resolution | VERIFIED | `AB6 OS!A131:M141`, `AB14!A42:BG46` |
| Underlying references | VERIFIED | `AB6 OS!G131:H141`, `AB6 OS!M145:X149`, `AB6 OS!R152:Z157` |
| Contract selection | VERIFIED | `AB6 OS!G131:I141`, `AB11!E12:X12` |
| Expiry selection | VERIFIED_WITH_INSTRUMENT_MASTER_RULE | `AB2!V27:AA27`, `AB11!E12:P12`; trading-date instrument master required |
| Strike range | VERIFIED_WITH_INSTRUMENT_MASTER_RULE | `AB6 OS!G131:G141`; strike interval resolved from instrument master |
| Premium filter | VERIFIED | `AB6 OS!H131:H141`, `AB6 OS!T145:V149` |
| OI filter | VERIFIED | `AB6 OS!I131:I141`, `AB6 OS!W145:W149` |
| Base Entry | VERIFIED | `AB6 OS!M131:M141`, `AB14!F42:BG46` |
| ORPT | VERIFIED | `AB6 OS!D144:L147` |
| RC | VERIFIED | `AB6 OS!M145:X149` |
| Missed Entry | VERIFIED | `AB6 OS!E144:E147` |
| Effective Entry | VERIFIED | `AB6 OS!X145:X149` |
| Target | VERIFIED | `AB6 OS!O131:O141`, `AB14!F42:BG46` |
| Original SL/MSL | VERIFIED | `AB6 OS!M132:M141`, `AB14!F42:BG46` |
| FSL/TRP | VERIFIED | `AB6 OS!M153:M157` |
| APS / staged exits | NOT_APPLICABLE | Global Option Selling one-lot APS clarification |
| EOD exit | VERIFIED | `AB6 OS!F159:J159`, `AB6 OS!Q159:U159` |
| Carry-forward | VERIFIED | `AB6 OS!F160:J160`, `AB6 OS!Q160:U160` |
| Equality | USER_CLARIFIED | Global Option Selling EOD equality rule |
| Next-day carried lifecycle | VERIFIED | `AB6 OS!B151:Z160` |
| Position protection | VERIFIED | `AB6 OS!B151:Z157`; carried-position invariant |
| Accounting/P&L unit | VERIFIED_WITH_INSTRUMENT_MASTER_RULE | `AB11!H12/K12`, `AB16!I90:W91`; lot size resolved by trading date |
| Quantity/Lot handling | VERIFIED_WITH_INSTRUMENT_MASTER_RULE | one lot from workbook; runtime resolves exchange units from lot size |
| Stock universe | USER_CLARIFIED_ARCHITECTURE_READY | AB8/AB10 support universe; instrument master supplies current eligibility; enabled subset pending |

Checklist rows use verified, not-applicable, or explicit blocked statuses.
Only operator symbol selection remains an implementation blocker.
