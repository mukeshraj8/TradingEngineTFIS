# Historical Backtest Report

- Strategy path: `config\strategies\options_sell\nifty\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Strategy root: `-`
- Shared data root: `-`
- Strategy code: `S23`
- Mode: `historical`
- EOD policy: `square_off_at_close`
- Monthly-status engine: `disabled`
- Validation status: `PASS`

This is offline simulation. It does not include brokerage, slippage, liquidity, or real fill modeling yet.

## Cost Assumptions

- slippage_points_per_side: `1.00`
- brokerage_points_per_trade: `0.50`
- other_cost_points_per_trade: `0.50`

## Summary Metrics

- total_evaluations: `6`
- accepted_candidates: `6`
- entered_trades: `5`
- expiry_day_candidates: `0`
- expiry_day_entered: `0`
- expiry_day_exit_satisfied: `0`
- expiry_day_exit_pending: `0`
- target_hits: `2`
- stoploss_hits: `2`
- eod_square_off: `1`
- carry_forward_pending: `0`
- no_entry: `1`
- no_exit: `0`
- total_gross_pnl_points: `-50.250`
- total_cost_points: `15.000`
- total_net_pnl_points: `-65.250`
- total_gross_pnl_rupees: `-2512.50`
- total_cost_rupees: `750.00`
- total_net_pnl_rupees: `-3262.50`
- total_pnl_points: `-50.250`
- average_pnl_points: `-10.050`
- average_net_pnl_points: `-13.050`
- average_net_pnl_rupees: `-652.50`
- win_rate: `40.00%`
- loss_rate: `60.00%`
- average_mfe: `85.94`
- average_mae: `70.46`

## Equity And Drawdown

- final_net_pnl_rupees: `-3262.50`
- max_drawdown_rupees: `15006.00`
- max_drawdown_points: `300.120`
- best_trade_net_rupees: `5955.00`
- worst_trade_net_rupees: `-5996.00`

## Trade Table

| Timestamp | Monthly Status | Selected Branches | Entry Price | Exit Price | Exit Reason | Gross PnL | Costs | Net PnL | Net Rupees | Cumulative Net Rupees | Drawdown Rupees | MFE | MAE | Bars Held |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-18T15:30:00 | - | - | 197.95 | 79.18 | TARGET_HIT | 118.770 | 3.000 | 115.770 | 5788.50 | 5788.50 | 0.00 | 122.95 | 7.05 | 2 |
| 2026-05-19T15:30:00 | - | - | 199.80 | 316.72 | STOPLOSS_HIT | -116.920 | 3.000 | -119.920 | -5996.00 | -207.50 | 5996.00 | 1.80 | 120.20 | 2 |
| 2026-05-20T15:30:00 | - | - | 201.65 | - | NO_ENTRY | - | - | - | - | - | - | - | - | 0 |
| 2026-05-21T15:30:00 | - | - | 202.57 | 260.00 | EOD_SQUARE_OFF | -57.425 | 3.000 | -60.425 | -3021.25 | -3228.75 | 9017.25 | 52.57 | 97.43 | 3 |
| 2026-05-22T15:30:00 | - | - | 198.88 | 315.65 | STOPLOSS_HIT | -116.775 | 3.000 | -119.775 | -5988.75 | -9217.50 | 15006.00 | 123.88 | 121.12 | 1 |
| 2026-05-23T15:30:00 | - | - | 203.50 | 81.40 | TARGET_HIT | 122.100 | 3.000 | 119.100 | 5955.00 | -3262.50 | 9051.00 | 128.50 | 6.50 | 2 |
