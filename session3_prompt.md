# Session 3: Circular Arbitrage, Options Strategy, and Full Test Suite

Read CLAUDE.md first for full competition context.

Do not ask questions — make reasonable decisions and proceed.

## Context

Session 1 built the foundation: datamodel stub, utilities (math, orderbook, position), Trader skeleton with Logger, `strategy_market_make_fixed`, `strategy_market_make_ema`.

Session 2 implemented: `strategy_pairs_arb`, `strategy_informed_trader`, `strategy_cross_exchange`, plus initial tests.

Two strategy stubs remain in `trader.py`: `strategy_circular_arb` and `strategy_options`. This session implements both and builds a comprehensive test suite.

---

## Task 1: Implement `strategy_circular_arb` in trader.py

This finds and exploits circular arbitrage opportunities across multiple products acting as exchange rates. In Prosperity 3 Round 1, products represented FX-like conversion rates between island goods.

**How circular arb works in Prosperity:**
- You have N products, each representing a "conversion rate" (e.g., product A lets you exchange good X for good Y at a certain rate).
- If you can chain A→B→C→A and end up with more than you started, that's a profitable cycle.
- In Prosperity, you can't literally chain conversions — instead, you simultaneously trade the legs: buy the underpriced legs, sell the overpriced legs.
- The strategy detects when the product of rates around a cycle exceeds 1.0 (or equivalently, when the sum of log-rates is positive).

**Requirements:**
- Config accepts: `cycle` (list of product symbols forming the arbitrage cycle, in order), `rate_type` (either `"mid"` or `"best"` — use mid prices or executable best bid/ask), `min_profit_bps` (minimum profit in basis points to trigger, e.g. 10 = 0.1%), `max_order_size`.
- Each timestep: compute the effective rate for each leg of the cycle from the order book. Calculate the round-trip profit. If profit > min_profit_bps, generate orders for all legs simultaneously.
- For executable rates: use best_ask when buying a leg, best_bid when selling.
- This strategy operates on the CURRENT product in the cycle (the one being dispatched from run()). It reads other products' order books from `state.order_depths` to compute the cycle profit, but only places orders for its own product.
- Persist nothing in traderData — this is a pure snapshot strategy.

**Important design note:** Since each product in the cycle gets its own `strategy_circular_arb` call from the run() dispatcher, each call only generates orders for that one product. The cycle profit calculation is shared — it reads all legs from state. To avoid computing the cycle N times, you can cache the cycle computation in `self.state_data["_circular_arb_cache"]` keyed by timestamp, and reuse it across products within the same timestep.

**Example PRODUCT_CONFIG entries (all legs of a cycle share the same cycle definition):**
```python
"PRODUCT_A": {
    "strategy": "circular_arb",
    "position_limit": 50,
    "cycle": ["PRODUCT_A", "PRODUCT_B", "PRODUCT_C"],
    "rate_type": "best",
    "min_profit_bps": 10,
    "max_order_size": 20,
    "cycle_role": "buy",   # "buy" or "sell" for this leg
},
```

If the cycle structure in P4 turns out to be different (e.g., products are literal exchange rates rather than tradeable assets), the strategy can be adapted. The core cycle-detection logic should be reusable.

---

## Task 2: Implement `strategy_options` in trader.py

This prices options using Black-Scholes, trades implied volatility mean reversion, and delta-hedges with the underlying. In Prosperity 3, Volcanic Rock Vouchers were call options on Volcanic Rock at various strikes.

**Requirements:**

### 2a: Add Black-Scholes utility functions

Add these as inlined helpers in trader.py (in the utility functions section near the top), AND as a new file `utils/options_utils.py`:

- `bs_call_price(S, K, T, r, sigma)` — Black-Scholes call price. S=spot, K=strike, T=time to expiry (in years), r=risk-free rate, sigma=volatility.
- `bs_put_price(S, K, T, r, sigma)` — Black-Scholes put price (via put-call parity: P = C - S + K*e^(-rT)).
- `bs_delta(S, K, T, r, sigma)` — Call delta (dC/dS = N(d1)).
- `implied_vol(market_price, S, K, T, r, option_type="call")` — Numerically solve for sigma using bisection. Search range [0.01, 5.0], tolerance 0.001, max 50 iterations. Return None if no convergence.
- Use `math.erf` for the normal CDF: `N(x) = 0.5 * (1 + math.erf(x / math.sqrt(2)))`.
- All functions must use only `math` — no scipy, no numpy required.

### 2b: Implement the strategy

- Config accepts: `underlying` (symbol of the underlying, e.g. "VOLCANIC_ROCK"), `strike` (int), `expiry_days` (days to expiry, converted to years as T = expiry_days/252), `risk_free_rate` (float, e.g. 0.0), `iv_window` (rolling window for IV mean reversion, e.g. 20), `iv_z_entry` (z-score threshold for IV trades, e.g. 1.5), `iv_z_exit` (e.g. 0.5), `delta_hedge` (bool, whether to also hedge with underlying).
- Each timestep:
  1. Get underlying mid price (S) from `state.order_depths[config["underlying"]]`.
  2. Get option mid price from `state.order_depths[product]`.
  3. Compute implied vol from the option mid price.
  4. Track IV history in traderData (capped at iv_window).
  5. Compute z-score of current IV vs rolling history.
  6. **If IV z > iv_z_entry**: IV is high → sell options (expect IV to drop, options overpriced).
  7. **If IV z < -iv_z_entry**: IV is low → buy options (expect IV to rise, options underpriced).
  8. **If |IV z| < iv_z_exit**: unwind toward flat.
  9. Optionally: compute delta and generate hedging orders for the underlying. The underlying orders should be returned separately — add them to `result[underlying]` by returning them in a special way (document your approach in a code comment).

**Hedging note:** Since each strategy call only returns orders for one product, delta hedging the underlying requires a design decision. The cleanest approach: have the options strategy also write a "hedge_orders" entry into `self.state_data` which the run() method picks up and appends to the underlying product's orders after the main loop. Implement this mechanism in run().

**Example PRODUCT_CONFIG entry:**
```python
"VOLCANIC_ROCK_VOUCHER_10000": {
    "strategy": "options",
    "position_limit": 200,
    "underlying": "VOLCANIC_ROCK",
    "strike": 10000,
    "expiry_days": 5,
    "risk_free_rate": 0.0,
    "iv_window": 20,
    "iv_z_entry": 1.5,
    "iv_z_exit": 0.5,
    "delta_hedge": True,
},
```

---

## Task 3: Build comprehensive test suite

Create `tests/test_all_strategies.py` that consolidates and extends all strategy tests. Structure:

```
tests/
├── __init__.py
├── helpers.py          # Shared mock builders
└── test_all_strategies.py
```

### tests/helpers.py
Build reusable mock factories:
- `make_order_depth(bids: dict, asks: dict) -> OrderDepth`
- `make_trade(symbol, price, qty, buyer, seller, timestamp) -> Trade`
- `make_state(traderData, timestamp, products_config, positions=None, market_trades=None, observations=None) -> TradingState` — builds a complete TradingState from a compact config dict describing each product's order book.
- `run_trader(state, product_config=None) -> (result, conversions, traderData)` — creates a Trader, optionally overrides PRODUCT_CONFIG, and runs one timestep.

### Tests to include:

**Market making (fixed):**
1. Quotes symmetrically around fair value at zero inventory.
2. Skews quotes when holding a position (long → wider bid, tighter ask).
3. Takes mispriced orders (asks below fair value, bids above).
4. Respects position limits — never generates orders that would exceed the limit.

**Market making (EMA):**
5. EMA initializes correctly on first timestep (empty traderData).
6. EMA updates and persists in traderData across timesteps.
7. Quotes adjust as EMA shifts.

**Pairs arb:**
8. Sells basket when spread z-score > z_entry (basket overpriced).
9. Buys basket when spread z-score < -z_entry (basket underpriced).
10. Unwinds position when |z| < z_exit.
11. Handles missing component order books gracefully (returns empty orders).

**Informed trader:**
12. Buys aggressively when tracked trader is net buying above threshold.
13. Sells aggressively when tracked trader is net selling below threshold.
14. Falls back to passive quoting when no signal.
15. Correctly aggregates flow across multiple timesteps via traderData.

**Cross-exchange:**
16. Generates buy orders + positive conversions when local ask < implied bid.
17. Generates sell orders + negative conversions when local bid > implied ask.
18. Does nothing when no arbitrage exists.

**Circular arb:**
19. Generates orders when cycle profit exceeds min_profit_bps.
20. Does nothing when cycle is not profitable.

**Options:**
21. `bs_call_price` matches a known test case (e.g., S=100, K=100, T=1, r=0.05, sigma=0.2 → ~10.45).
22. `implied_vol` recovers sigma when given the BS price as input.
23. `bs_delta` is between 0 and 1 for a call, increases as S increases.
24. Strategy buys options when IV z-score is below -z_entry.
25. Strategy sells options when IV z-score is above z_entry.

**Infrastructure:**
26. traderData round-trips correctly (serialize → deserialize → serialize produces same result).
27. Position clipper rejects orders that would exceed limits.
28. Logger produces valid JSON output.

Run all tests with: `python -m pytest tests/ -v` (install pytest if needed: `pip install pytest`).

---

## Task 4: Update inlined utilities in trader.py

Make sure trader.py remains self-contained:
- Inline the Black-Scholes functions (`bs_call_price`, `bs_put_price`, `bs_delta`, `implied_vol`, `norm_cdf`) near the top of trader.py with the other utility functions.
- If any new helpers were needed for circular arb, inline those too.
- Run `python scripts/merge_to_submission.py` and confirm all checks pass.

---

## Task 5: Create a .gitignore

Create a `.gitignore` at the repo root:
```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
.venv/
venv/
.env
data/
backtests/
*.log
submission/
```

---

## Deliverables

1. All tests pass: `python -m pytest tests/ -v`
2. Submission check passes: `python scripts/merge_to_submission.py`
3. Commit: `git add -A && git commit -m "Session 3: circular arb, options strategy, full test suite"`
