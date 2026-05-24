# S23 Branch Mapping

This document records how the shared Excel `S23` block in `AB6 OS` maps to the
four normalized folder-based TFIS strategy folders.

Shared workbook identity:

- `AB2!B28 = S23`
- `AB6 OS!C163 = S23`
- `AB6 OS!C164 = NIFTY_OP_SELL_WK_DIFF_2D_3D`

Normalized folder strategy mapping:

| Folder Strategy | Workbook Branch | Rows | Monthly Status Source | Option Type Source |
| --- | --- | --- | --- | --- |
| `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D` | Bull / Bull CF Call | `162-163` | `D162` | `F162` |
| `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT` | Bull / Bull CF Put | `165-166` | `D162` | `F165` |
| `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL` | Bear / Bear CF Call | `168-169` | `D168` | `F168` |
| `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` | Bear / Bear CF Put | `171-172` | `D168` | `F171` |

Notes:

- The workbook stores these as one shared S23 rule block.
- The folder-based TFIS layout splits them into separate strategy folders so
  each branch can be validated, backtested, and reviewed independently.
- The branch-specific folder `unique_code` values append a branch suffix for
  normalized config uniqueness, even though the workbook identity anchor uses
  the shared base code `NIFTY_OP_SELL_WK_DIFF_2D_3D`.
