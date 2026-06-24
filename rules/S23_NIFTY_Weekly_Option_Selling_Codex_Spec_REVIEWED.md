# S23 Corrected Codex Strategy Specification

## Purpose

This document is the corrected implementation specification for strategy **S23 – NIFTY Weekly Option Selling**.

It is based on the attached **Nifty Weekly Option Selling Rules** sheet and should override earlier inferred S23 documentation where conflicts exist.

The main correction is: **do not infer DLL/DHH mapping from bullish/bearish theory alone. Use the explicit branch matrix below.**

---

# 1. Strategy Identity

| Field | Value |
|---|---|
| Strategy Code | S23 |
| Symbol | NIFTY only |
| Segment | Options Sell |
| Expiry | Weekly |
| Instrument | NIFTY weekly options |
| BANKNIFTY weekly selling | Not supported |
| Current NIFTY lot size | 65 |
| Minimum OI rule | 500 lots = 32,500 contracts |

---

# 2. Monthly Status Groups

Treat statuses as two groups:

```text
BULLISH_GROUP = {BULLISH, BULLISH_CONFIRMED, BULL, BULL_CF}
BEARISH_GROUP = {BEARISH, BEARISH_CONFIRMED, BEAR, BEAR_CF}
```

Implementation should normalize workbook/user labels into these two groups.

---

# 3. Correct Branch Matrix

This matrix is the highest-priority rule for S23.

| Monthly Status Group | Option Side | Trade | Spot Reference | Stoploss Structure Reference | Stoploss Buffer |
|---|---|---|---|---|---|
| Bullish / Bullish Confirmed | CE | Sell Call | 3DLL | Previous 2DHH | +7% |
| Bullish / Bullish Confirmed | PE | Sell Put | 2DHH | Previous 3DHH | +10% |
| Bearish / Bearish Confirmed | CE | Sell Call | 2DLL | Previous 3DHH | +10% |
| Bearish / Bearish Confirmed | PE | Sell Put | 3DHH | Previous 2DHH | +7% |

Important correction:

```text
Bearish CE uses 2DLL, not 2DHH.
```

Do not replace this with directional inference.

---

# 4. Trading Day Preparation

Before calculating trades:

1. Write down date, day, and preparation time.
2. Check Monthly Status from the futures continuous graph.
3. Normalize Monthly Status into Bullish Group or Bearish Group.
4. Collect required spot references:
   - 2DLL
   - 3DLL
   - 2DHH
   - 3DHH
5. Collect option-chain data for near weekly contract.
6. If near contract fails qualification, check next weekly contract.

---

# 5. Strike Range Rules

## 5.1 Bullish Group – CE Sell

Reference:

```text
REF = 3DLL of Spot
```

Start Strike:

```text
START = round_down_to_strike(REF + 5% of REF)
```

End Strike:

```text
END = round_down_to_strike(REF) - 1 strike_step
```

Search direction for ideal premium:

```text
START -> END
```

Search direction for minimum premium:

```text
END -> START
```

---

## 5.2 Bullish Group – PE Sell

Reference:

```text
REF = 2DHH of Spot
```

Start Strike:

```text
START = round_up_to_strike(REF - 5% of REF)
```

End Strike:

```text
END = round_up_to_strike(REF) + 1 strike_step
```

Search direction for ideal premium:

```text
START -> END
```

Search direction for minimum premium:

```text
END -> START
```

---

## 5.3 Bearish Group – CE Sell

Reference:

```text
REF = 2DLL of Spot
```

Start Strike:

```text
START = round_down_to_strike(REF + 5% of REF)
```

End Strike:

```text
END = round_down_to_strike(REF) - 1 strike_step
```

Search direction for ideal premium:

```text
START -> END
```

Search direction for minimum premium:

```text
END -> START
```

---

## 5.4 Bearish Group – PE Sell

Reference:

```text
REF = 3DHH of Spot
```

Start Strike:

```text
START = round_up_to_strike(REF - 5% of REF)
```

End Strike:

```text
END = round_up_to_strike(REF) + 1 strike_step
```

Search direction for ideal premium:

```text
START -> END
```

Search direction for minimum premium:

```text
END -> START
```

---

# 6. Premium Qualification Rules

For each branch:

```text
IDEAL_PREMIUM = REF * 1.20%
MIN_PREMIUM   = REF * 0.90%
```

A candidate strike is eligible only if its option premium satisfies the relevant premium qualification rule from the rule sheet.

Recommended implementation:

```text
ideal_qualified    = option_premium >= IDEAL_PREMIUM
minimum_qualified  = option_premium >= MIN_PREMIUM
```

Use the rule-sheet search flow:

1. First search near contract from START to END for the first strike satisfying ideal premium criteria.
2. Then search near contract from END to START for the first strike satisfying minimum premium criteria.
3. If no qualifying strike exists in near contract, repeat both searches in next contract.
4. If still no qualifying strike exists, do not place order for that side on that day.

Do not select a strike by closest distance alone.
Premium qualification is mandatory.

---

# 7. OI Qualification

Minimum OI from rule sheet:

```text
500 lots
```

Current NIFTY lot size:

```text
65
```

Therefore:

```text
MIN_OI_CONTRACTS = 500 * 65 = 32500
```

A strike is tradable only if:

```text
strike_oi >= 32500
```

Codex must not use old NIFTY lot size values.

---

# 8. Entry Rules

Entry order side:

```text
SO = Sell Order
```

Entry calculation:

```text
ENTRY = previous_option_premium_at_reference - 7.50%
ENTRY = previous_option_premium_at_reference * 0.925
```

Branch-specific entry references:

| Monthly Status Group | Option Side | Entry Reference |
|---|---|---|
| Bullish Group | CE | Previous 3DLL option premium - 7.50% |
| Bullish Group | PE | Previous 2DLL option premium - 7.50% |
| Bearish Group | CE | Previous 2DLL option premium - 7.50% |
| Bearish Group | PE | Previous 3DLL option premium - 7.50% |

---

# 9. Target Rules

Target order side:

```text
BO = Buy Order
```

Target calculation for both CE and PE:

```text
TARGET = ENTRY - 60% of ENTRY
TARGET = ENTRY * 0.40
```

Branch-specific wording:

```text
Call Target = Call Sell Entry - 60%
Put Target  = Put Sell Entry - 60%
```

---

# 10. Stoploss Rules

Stoploss order side:

```text
BO = Buy Order
```

General form:

```text
PERCENT_SL = ENTRY + 60% of ENTRY
PERCENT_SL = ENTRY * 1.60

STRUCTURE_SL = previous_structure_option_premium * (1 + buffer)

FINAL_SL = min(PERCENT_SL, STRUCTURE_SL)
```

Branch-specific stoploss rules:

## 10.1 Bullish Group – CE Sell

```text
PERCENT_SL  = Call Sell Entry * 1.60
STRUCTURE_SL = Previous 2DHH option premium * 1.07
FINAL_SL = min(PERCENT_SL, STRUCTURE_SL)
```

## 10.2 Bullish Group – PE Sell

```text
PERCENT_SL  = Put Sell Entry * 1.60
STRUCTURE_SL = Previous 3DHH option premium * 1.10
FINAL_SL = min(PERCENT_SL, STRUCTURE_SL)
```

## 10.3 Bearish Group – CE Sell

```text
PERCENT_SL  = Call Sell Entry * 1.60
STRUCTURE_SL = Previous 3DHH option premium * 1.10
FINAL_SL = min(PERCENT_SL, STRUCTURE_SL)
```

## 10.4 Bearish Group – PE Sell

```text
PERCENT_SL  = Put Sell Entry * 1.60
STRUCTURE_SL = Previous 2DHH option premium * 1.07
FINAL_SL = min(PERCENT_SL, STRUCTURE_SL)
```

---

# 11. Contract Qualification Flow

For each required side, CE and PE:

```text
1. Calculate branch REF.
2. Calculate START and END strike.
3. Search near contract START -> END for first ideal premium qualifying strike.
4. Search near contract END -> START for first minimum premium qualifying strike.
5. Apply OI qualification.
6. If near contract has no qualifying strike, repeat steps 3-5 in next contract.
7. If no qualifying strike in near or next contract, do not place order for that side.
```

Do not silently fallback to an unqualified strike.

---

# 12. Order Generation

For every valid side:

```text
Entry  = SO at ENTRY
Target = BO at TARGET
SL     = BO at FINAL_SL
```

Both CE and PE can be generated for the same day if both qualify.

If only one side qualifies, only that side should be generated.

---

# 13. Explicit Do-Not-Implement Rules

Codex must not do the following:

1. Do not support BANKNIFTY weekly option selling for S23.
2. Do not use old NIFTY lot size.
3. Do not infer Bearish CE reference as 2DHH.
4. Do not infer that all CE rules use DHH or all PE rules use DLL.
5. Do not select strike purely by distance from spot.
6. Do not place an order when both near and next contract fail qualification.
7. Do not treat workbook copy-paste formulas as unquestionable if they contradict the rule-sheet branch matrix.
8. Do not hardcode branch logic in scattered files; centralize this matrix in strategy configuration or a single strategy-rule module.

---

# 14. Suggested Config Shape

```yaml
strategy_code: S23
symbol: NIFTY
expiry: WEEKLY
segment: OPTIONS_SELL
lot_size: 65
min_oi_lots: 500
min_oi_contracts: 32500

monthly_status_groups:
  bullish: [BULLISH, BULLISH_CONFIRMED, BULL, BULL_CF]
  bearish: [BEARISH, BEARISH_CONFIRMED, BEAR, BEAR_CF]

branches:
  bullish:
    CE:
      trade: SELL_CALL
      spot_reference: 3DLL
      strike_start:
        basis: spot_reference_plus_5_percent
        rounding: down
      strike_end:
        basis: spot_reference_minus_1_strike
        rounding: down
      entry_reference: previous_3DLL_option_premium
      entry_multiplier: 0.925
      target_multiplier: 0.40
      percent_sl_multiplier: 1.60
      structure_sl_reference: previous_2DHH_option_premium
      structure_sl_multiplier: 1.07
      final_sl: min(percent_sl, structure_sl)

    PE:
      trade: SELL_PUT
      spot_reference: 2DHH
      strike_start:
        basis: spot_reference_minus_5_percent
        rounding: up
      strike_end:
        basis: spot_reference_plus_1_strike
        rounding: up
      entry_reference: previous_2DLL_option_premium
      entry_multiplier: 0.925
      target_multiplier: 0.40
      percent_sl_multiplier: 1.60
      structure_sl_reference: previous_3DHH_option_premium
      structure_sl_multiplier: 1.10
      final_sl: min(percent_sl, structure_sl)

  bearish:
    CE:
      trade: SELL_CALL
      spot_reference: 2DLL
      strike_start:
        basis: spot_reference_plus_5_percent
        rounding: down
      strike_end:
        basis: spot_reference_minus_1_strike
        rounding: down
      entry_reference: previous_2DLL_option_premium
      entry_multiplier: 0.925
      target_multiplier: 0.40
      percent_sl_multiplier: 1.60
      structure_sl_reference: previous_3DHH_option_premium
      structure_sl_multiplier: 1.10
      final_sl: min(percent_sl, structure_sl)

    PE:
      trade: SELL_PUT
      spot_reference: 3DHH
      strike_start:
        basis: spot_reference_minus_5_percent
        rounding: up
      strike_end:
        basis: spot_reference_plus_1_strike
        rounding: up
      entry_reference: previous_3DLL_option_premium
      entry_multiplier: 0.925
      target_multiplier: 0.40
      percent_sl_multiplier: 1.60
      structure_sl_reference: previous_2DHH_option_premium
      structure_sl_multiplier: 1.07
      final_sl: min(percent_sl, structure_sl)

premium_rules:
  ideal_premium_multiplier: 0.012
  minimum_premium_multiplier: 0.009
  near_contract_search:
    ideal_search_direction: start_to_end
    minimum_search_direction: end_to_start
  next_contract_search:
    use_if_near_contract_has_no_qualified_strike: true
```

---

# 15. Acceptance Tests Codex Should Add/Update

At minimum, add tests for these scenarios:

1. Bullish CE uses 3DLL, not 2DLL or 2DHH.
2. Bullish PE uses 2DHH for strike range and previous 2DLL option premium for entry.
3. Bearish CE uses 2DLL, not 2DHH.
4. Bearish PE uses 3DHH for strike range and previous 3DLL option premium for entry.
5. NIFTY lot size 65 produces minimum OI 32,500 contracts.
6. Target is ENTRY * 0.40.
7. Entry is previous reference premium * 0.925.
8. SL is min(ENTRY * 1.60, structure reference premium with correct 7% or 10% buffer).
9. No order is generated when near and next contracts both fail qualification.
10. BANKNIFTY weekly S23 config is rejected or unsupported.
