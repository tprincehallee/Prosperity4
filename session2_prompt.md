# Session 2: Advanced Strategies — Pairs Arb, Informed Trader Detector, Circular Arb

Read CLAUDE.md first — it has the full competition rules, datamodel reference, and strategy context.

## Context

Session 1 built the foundation:
- `datamodel.py` — local dev stub for the competition's types
- `utils/math_utils.py` — EMA, z-score, VWAP, linear regression, Bollinger bands
- `utils/orderbook_utils.py` — best bid/ask, mid, Wall Mid, book imbalance, net_trade_flow
- `utils/position_utils.py` — position clipper, inventory skew, max buy/sell qty
- `trader.py` — Trader class with run() dispatch, Logger (Visualizer-compatible), state serialization, and two working strategies: `strategy_market_make_fixed` and `strategy_market_make_ema`

Five strategy methods in `trader.py` are currently stubbed with `return [], 0`. This session implements three of them.

## Task 1: Implement `strategy_pairs_arb` in trader.py

This strategy trades the spread between an ETF/basket product and its components. In Prosperity 3, PICNIC_BASKET1 = 6×CROISSANTS + 3×JAMS + 1×DJEMBES, and PICNIC_BASKET2 = 4×CROISSANTS + 2×JAMS.

**Requirements:**
- Config should accept: `components` (dict mapping component symbol -> weight), `z_entry` (z-score threshold to enter, e.g. 2.0), `z_exit` (threshold to exit, e.g. 0.5), `spread_window` (rolling window for z-score, e.g. 50), and `max_order_size`.
- Each timestep: compute basket NAV from component mid prices × weights, compute spread = basket_mid - NAV, track spread history in `traderData`, compute rolling z-score.
- When z > z_entry: basket is overpriced → sell basket, buy components proportionally.
- When z < -z_entry: basket is underpriced → buy basket, sell components.
- When |z| < z_exit and we have a position: unwind toward flat.
- All orders must go through `clip_orders` for position limit compliance.
- Persist spread history (as a list, capped at spread_window length) in traderData under the product key.

**Example PRODUCT_CONFIG entry:**
```python
"PICNIC_BASKET1": {
    "strategy": "pairs_arb",
    "position_limit": 60,
    "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
    "z_entry": 2.0,
    "z_exit": 0.5,
    "spread_window": 50,
    "max_order_size": 10,
},
```

## Task 2: Implement `strategy_informed_trader` in trader.py

This detects and follows "informed" bots that trade with advance knowledge of price direction. In Prosperity 3 Round 5, a bot named "Olivia" was an informed trader — tracking her net flow predicted short-term price moves.

**Requirements:**
- Config should accept: `tracked_traders` (list of trader IDs to monitor, e.g. ["Olivia"]), `flow_window` (number of timesteps to aggregate flow over, e.g. 10), `signal_threshold` (net flow threshold to trigger directional trade, e.g. 5), `base_spread` (for passive quoting when no signal).
- Each timestep: scan `state.market_trades[product]` for trades involving tracked traders. Compute net flow (bought qty - sold qty) for each tracked trader. Aggregate flow over the rolling window (persist in traderData).
- **Signal logic:**
  - If aggregate net flow > signal_threshold: informed trader is buying → aggressively buy (take asks up to fair value + small premium).
  - If aggregate net flow < -signal_threshold: informed trader is selling → aggressively sell (take bids down to fair value - small premium).
  - Otherwise: fall back to passive market making around Wall Mid / EMA fair value.
- The `net_trade_flow` helper already exists in the codebase (both in `utils/orderbook_utils.py` and inlined in `trader.py`). Use it.
- Persist per-trader flow history in traderData.

**Example PRODUCT_CONFIG entry:**
```python
"SQUID_INK": {
    "strategy": "informed_trader",
    "position_limit": 50,
    "tracked_traders": ["Olivia"],
    "flow_window": 10,
    "signal_threshold": 5,
    "base_spread": 2,
    "ema_alpha": 0.3,
},
```

## Task 3: Implement `strategy_cross_exchange` in trader.py

This exploits arbitrage between a local exchange and a foreign exchange via the conversion mechanism. In Prosperity 3, Magnificent Macarons were tradeable locally and on a foreign exchange with tariffs and transport fees.

**Requirements:**
- Config should accept: `conversion_product` (the symbol in `state.observations.conversionObservations`), `storage_cost` (per-unit per-timestep cost, default 0), `spread_buffer` (extra margin to ensure profitability, e.g. 1.0), `max_conversion` (max units to convert per timestep).
- Each timestep: read the ConversionObservation for the product. Compute:
  - `implied_bid = obs.bidPrice - obs.exportTariff - obs.transportFees - storage_cost`
  - `implied_ask = obs.askPrice + obs.importTariff + obs.transportFees`
- If local best_ask < implied_bid - spread_buffer: buy locally, request conversion to sell on foreign exchange → profit.
- If local best_bid > implied_ask + spread_buffer: sell locally, request conversion to buy from foreign exchange → profit.
- Return both orders AND the appropriate conversion count.
- Also post passive quotes around the implied mid to capture additional spread.

**Example PRODUCT_CONFIG entry:**
```python
"MAGNIFICENT_MACARONS": {
    "strategy": "cross_exchange",
    "position_limit": 75,
    "conversion_product": "MAGNIFICENT_MACARONS",
    "storage_cost": 0.1,
    "spread_buffer": 1.0,
    "max_conversion": 10,
},
```

## Task 4: Write tests

Create a file `tests/test_strategies.py` that tests all three new strategies:

1. **Pairs arb test**: Create mock TradingState with a basket and components where the basket is overpriced (spread z > 2). Verify the strategy generates sell orders for the basket. Then test the underpriced case. Then test the unwind case.

2. **Informed trader test**: Create mock TradingState with market_trades showing "Olivia" buying heavily. Verify the strategy generates aggressive buy orders. Test the selling signal too. Test fallback to passive quoting when no signal.

3. **Cross-exchange test**: Create mock TradingState with a ConversionObservation where the implied bid is above the local ask. Verify the strategy generates buy orders and a positive conversion count.

Use the same mock TradingState construction pattern already validated in Session 1 (create OrderDepth, Listing, Observation objects directly).

## Task 5: Update the inlined utility functions

The strategies above may need utility functions that exist in `utils/` but aren't yet inlined in `trader.py`. Make sure any new helpers used by the strategies are also present as inlined functions in `trader.py` (near the top, in the utility functions section), since `trader.py` must be self-contained for submission.

## Constraints

- Everything in trader.py must use only allowed imports: `datamodel`, `json`, `math`, `typing`, `collections`, `statistics`, `numpy`, `pandas`, `jsonpickle`.
- All strategies must return `Tuple[List[Order], int]` (orders, conversions).
- All orders must be clipped via `clip_orders` before being returned from `run()`.
- Prices are integers. Use `int(round(...))` when converting from float fair values.
- Handle empty order books gracefully (check before accessing keys).
- Handle empty/missing traderData on first timestep.
- Keep each strategy method under ~80 lines for readability.

## Deliverables

After completing all tasks:
1. Run `python tests/test_strategies.py` and confirm all tests pass.
2. Run `python scripts/merge_to_submission.py` and confirm no warnings.
3. Commit: `git add -A && git commit -m "Session 2: pairs arb, informed trader, cross-exchange strategies"`
