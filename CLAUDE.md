# CLAUDE.md — IMC Prosperity 4 Competition Toolkit

## Project Purpose

This repository contains all tools, strategies, and analysis code for competing in **IMC Prosperity 4** (April 2026), a 15-day, 5-round algorithmic trading competition hosted by IMC Trading. The goal is to maximize PnL (profit in SeaShells) across all rounds by writing a Python trading algorithm that trades against bots in a simulated market.

Competition site: https://prosperity.imc.com

---

## Simulation Rules & Environment

### Algorithm Format

- **Single Python file** submission containing a `Trader` class.
- The `Trader` class must have a `run(self, state: TradingState)` method.
- `run()` is called once per timestep with the current market state.
- `run()` must return a 3-tuple: `(result, conversions, traderData)`
  - `result`: `dict[str, list[Order]]` — orders keyed by product symbol
  - `conversions`: `int` — number of conversion requests (for cross-exchange products)
  - `traderData`: `str` — JSON string persisted and passed back next timestep
- **Timeout**: < 900ms per `run()` call.
- **Allowed imports**: `pandas`, `numpy`, `statistics`, `math`, `typing`, `jsonpickle`, `json`, `collections`, and the provided `datamodel` module.
- **No external network access, no filesystem access.**

### Datamodel (from `datamodel.py`)

```python
# Key classes you will use:

class Order:
    def __init__(self, symbol: str, price: int, quantity: int):
        # quantity > 0 = buy order, quantity < 0 = sell order
        pass

class OrderDepth:
    buy_orders: dict[int, int]   # price -> positive quantity
    sell_orders: dict[int, int]  # price -> negative quantity

class Trade:
    symbol: str
    price: int
    quantity: int
    buyer: str      # trader ID (e.g., "Olivia", "Vinnie", "YOU")
    seller: str
    timestamp: int

class TradingState:
    timestamp: int
    traderData: str                              # your persisted state from last timestep
    listings: dict[str, Listing]                 # symbol -> Listing (product, denomination)
    order_depths: dict[str, OrderDepth]          # symbol -> current order book
    own_trades: dict[str, list[Trade]]           # symbol -> your fills since last timestep
    market_trades: dict[str, list[Trade]]        # symbol -> other participants' trades
    position: dict[str, int]                     # symbol -> current position
    observations: Observation                    # external signals (e.g., humidity, sunlight)

class Observation:
    plainValueObservations: dict[str, float]     # signal_name -> value
    conversionObservations: dict[str, ConversionObservation]

class ConversionObservation:
    bidPrice: float
    askPrice: float
    transportFees: float
    exportTariff: float
    importTariff: float
    sugarPrice: float      # example; fields vary by product
    sunlightIndex: float
```

### Order Matching Rules

1. At the start of each timestep, **all previous orders are cleared** (no persistent orders).
2. The simulation processes new orders sequentially: deep-liquidity makers first, then some takers, then YOUR orders, then remaining bots.
3. **Speed and cancellation are irrelevant** — you see a full snapshot and submit any combination of passive or aggressive orders.
4. Buy orders match against sell orders in the book at the **order's price** (not the book's price).
5. If your order quantity exceeds available book volume, the remainder becomes a resting quote that bots may trade against within the same timestep.
6. Orders that would exceed position limits are rejected entirely.

### Position Limits

Each product has a hard position limit. Orders that would cause you to exceed the limit are **rejected** (not partially filled — entirely rejected). Always clip orders to stay within limits.

**Prosperity 3 position limits** (expect similar structure in P4):

| Product | Limit |
|---------|-------|
| RAINFOREST_RESIN | 50 |
| KELP | 50 |
| SQUID_INK | 50 |
| CROISSANTS | 250 |
| JAMS | 350 |
| DJEMBES | 60 |
| PICNIC_BASKET1 | 60 |
| PICNIC_BASKET2 | 100 |
| VOLCANIC_ROCK | 400 |
| VOLCANIC_ROCK_VOUCHER_* | 200 |
| MAGNIFICENT_MACARONS | 75 |

### State Persistence via traderData

- `traderData` is a string (max ~1MB) passed between timesteps.
- Use `json.dumps()` / `json.loads()` for serialization.
- Convert non-serializable types (e.g., `deque`) to lists before dumping.
- **First timestep**: `traderData` is an empty string `""`. Always handle this case.
- This is the ONLY way to maintain state across timesteps. Instance variables on the Trader class DO persist within a single simulation run, but `traderData` is the official/safe mechanism.

### Conversions (Cross-Exchange Products)

Some products (e.g., Macarons in P3) can be converted between a local and foreign exchange. The `ConversionObservation` provides foreign bid/ask plus tariffs and transport fees. You request conversions via the `conversions` return value. Implied prices:
- Implied Bid = `observation.bidPrice - observation.exportTariff - observation.transportFees - storageCost`
- Implied Ask = `observation.askPrice + observation.importTariff + observation.transportFees`

---

## Prosperity 3 Products & Strategy Archetypes

Understanding product archetypes is the single most important classification task at the start of each round. From P3:

### 1. Fixed Fair Value (Market Making)
**Example: Rainforest Resin** (true value ~10,000)
- Quote bid/ask around the known fair value.
- Skew quotes based on current inventory (shift prices toward unwinding position).
- Optimize the edge vs. fill probability trade-off.
- Typical spread: 2-4 ticks.

### 2. Random Walk / Trending (EMA Tracking)
**Example: Kelp**
- No fixed fair value; price follows a stochastic process.
- Use EMA or rolling regression to estimate current fair value.
- Market-make around the estimated fair value.
- Tighter spreads when confident, wider when uncertain.

### 3. Bot-Exploitable / Scalping
**Example: Squid Ink**
- Specific bots exhibit predictable patterns (e.g., mean-reversion signals, momentum signals).
- Detect patterns in `market_trades` (buyer/seller IDs, timing, volume).
- Trade directionally when a signal fires, revert to market-making otherwise.

### 4. ETF / Basket Arbitrage
**Example: Picnic Baskets (= weighted combination of Croissants, Jams, Djembes)**
- Compute theoretical basket value from components.
- Trade the spread when basket price deviates from NAV.
- **Cannot directly convert** baskets to/from components — must trade both legs.
- Use z-score of spread to trigger entries/exits.
- Hedge ratios: PICNIC_BASKET1 = 6×Croissants + 3×Jams + 1×Djembes; PICNIC_BASKET2 = 4×Croissants + 2×Jams.

### 5. Options / Volatility
**Example: Volcanic Rock Vouchers** (call options on Volcanic Rock)
- Price using Black-Scholes; compute implied volatility.
- Trade IV mean reversion (buy when IV is low, sell when high).
- Delta hedge with the underlying (Volcanic Rock).
- Multiple strikes available (9500, 9750, 10000, 10250, 10500 in P3).

### 6. Cross-Exchange / Locational Arbitrage
**Example: Magnificent Macarons**
- Product tradeable locally AND on a foreign exchange (via conversions).
- Compute implied local prices from foreign quotes + tariffs/fees.
- Exploit when local price crosses implied foreign price.
- Hidden "taker bot" behavior: a bot may aggressively buy/sell near certain price levels — detecting this pattern is extremely high-alpha.

### 7. Informed Trader Signals (The "Olivia" Pattern)
- **Critical insight**: Some bots trade with information about future price moves.
- In P3 Round 5, trader data revealed bot identities (e.g., "Olivia").
- By tracking a specific bot's net buying/selling, you can predict short-term direction.
- Top teams (Frankfurt Hedgehogs, 2nd place) generated ~100K+ SeaShells from this signal alone.
- **Detection method**: Track `market_trades`, filter by `buyer`/`seller` ID, compute net flow per bot, use as directional signal.
- Similar hidden taker behavior appeared in Orchids (P2) and Macarons (P3).

---

## Key Strategic Principles

These are hard-won insights from top-team writeups (Frankfurt Hedgehogs 2nd, Alpha Animals 9th, Linear Utility 2nd P2):

1. **Robustness over complexity**: Select parameters from flat regions of the performance landscape, not sharp peaks. A slightly suboptimal but stable strategy beats a fragile optimized one.
2. **Early and frequent submission**: Submit a working baseline ASAP each round. Iterate from there. The submission system can be slow near deadlines.
3. **Trade every product**: Even small edge per product compounds. Don't leave money on the table.
4. **Discord disinformation is real**: People post fake backtesting results and misleading strategies. Trust only your own analysis.
5. **Backtester ≠ live environment**: Bot behavior in backtests (which replay historical data) doesn't perfectly match live simulation. Use backtests for directional guidance, not absolute truth.
6. **Manual challenges are high-leverage**: Standalone math/probability puzzles worth significant points. Budget time for them.
7. **Detect bot patterns early**: Analyze `market_trades` data carefully each round. Plot every bot's behavior. Look for informed traders, mean-reverters, momentum chasers.
8. **Position management is critical**: Always clip orders to respect limits. Build the position clipper into your core infrastructure, not as an afterthought.

---

## Codebase Architecture

### Directory Structure
```
prosperity4/
├── CLAUDE.md                    # This file
├── trader.py                    # Main submission file (single file)
├── strategies/                  # Strategy modules (for development; merged into trader.py for submission)
│   ├── market_maker.py
│   ├── ema_follower.py
│   ├── pairs_arb.py
│   ├── informed_trader.py
│   ├── circular_arb.py
│   └── options_pricer.py
├── utils/                       # Utility functions
│   ├── math_utils.py            # EMA, z-score, VWAP, regression
│   ├── orderbook_utils.py       # Best bid/ask, mid, Wall Mid, spread, depth
│   └── position_utils.py        # Position clipper, order validator
├── analysis/                    # Jupyter notebooks for round analysis
│   ├── round_analysis_template.ipynb
│   └── parameter_landscape.ipynb
├── backtests/                   # Backtest results and logs
├── data/                        # Round data CSVs (downloaded each round)
└── scripts/
    ├── merge_to_submission.py   # Merge strategies/ + utils/ into single trader.py
    └── run_backtest.sh          # Wrapper for prosperity3bt / prosperity4bt
```

### Coding Conventions

- **All prices are integers** in the Prosperity environment. Don't use floats for prices.
- **Order quantities**: positive = buy, negative = sell (in `sell_orders` dict).
- **Always check for empty order books** before accessing `max(buy_orders.keys())` etc.
- **Use `collections.deque(maxlen=N)` for rolling windows** — auto-truncates.
- **JSON serialization**: Convert deques to lists, numpy arrays to lists, before `json.dumps()`.
- **No global state** — all state must flow through `traderData` or instance variables.
- **Keep `run()` under 900ms** — avoid expensive operations like large matrix inversions.
- **Use descriptive variable names**: `fair_value`, `spread_width`, `inventory_skew`, not `fv`, `sw`, `is`.
- **Log important values** via print statements (visible in the visualizer).

### Submission Merging

During development, code is split across files for modularity. For submission, everything must be merged into a single `trader.py`. The `merge_to_submission.py` script handles this by inlining all imports from `strategies/` and `utils/` into one file.

---

## Tools & Infrastructure

### Backtester
- **Jasper Merle's `prosperity3bt`**: `pip install -U prosperity3bt`
- Run: `prosperity3bt trader.py <round_number>`
- Visualizer: https://jmerle.github.io/imc-prosperity-3-visualizer/
- For P4, expect `prosperity4bt` or similar; the architecture will be very similar.
- Backtest env vars: `PROSPERITY3BT_ROUND`, `PROSPERITY3BT_DAY` (don't depend on these in submissions).

### Algorithm Validator
- **`imc-prospector`**: `pip install imc-prospector`
- Run: `imc-prospector check trader.py`
- Validates imports, return signature, and common mistakes before submission.

### Key Reference Repositories
- Frankfurt Hedgehogs (2nd, P3): https://github.com/TimoDiehm/imc-prosperity-3
- Alpha Animals (9th, P3): https://github.com/CarterT27/imc-prosperity-3
- Linear Utility (2nd, P2): https://github.com/ericcccsliu/imc-prosperity-2
- Prosperity 2 Manual Solutions: https://github.com/gabsens/IMC-Prosperity-2-Manual
- Zahcheesha Simulator (P1): https://github.com/MichalOkon/imc_prosperity

---

## Fair Value Estimation Methods

Use these in order of preference based on available information:

1. **Known constant** (e.g., Rainforest Resin = 10,000): Use directly.
2. **Wall Mid**: Volume-weighted midpoint — `(best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)`. More robust than simple mid when book is asymmetric.
3. **VWAP of recent trades**: Volume-weighted average price of last N trades.
4. **EMA of mid prices**: Exponential moving average with tunable alpha (e.g., 0.2–0.5).
5. **Linear regression**: Fit on last N mid prices, use extrapolated value.
6. **Basket NAV**: For ETF-like products, compute from component fair values.
7. **Black-Scholes**: For options, compute theoretical price from underlying, strike, vol, time-to-expiry.

---

## Round-by-Round Workflow

When a new round starts:

1. **Download data** immediately.
2. **Run analysis notebook**: Plot price series, volumes, correlations, bot signatures.
3. **Classify each new product** into an archetype (see above).
4. **Implement strategy** for new product; integrate with existing products.
5. **Backtest** — check PnL, check position limit compliance, check for crashes.
6. **Submit early** — get a baseline score, then iterate.
7. **Optimize parameters** — run grid search, check landscape stability.
8. **Analyze live results** from the submission dashboard.
9. **Solve manual challenge** — budget dedicated time for this.

---

## Common Pitfalls

- **Forgetting to handle empty `traderData`** on first timestep → crash.
- **Not clipping orders to position limits** → orders silently rejected.
- **Using floats for prices** → type mismatch errors.
- **Overfitting to backtest data** → poor live performance.
- **Ignoring `market_trades`** → missing high-alpha bot signals.
- **Breaking existing strategies** when adding new products → always test all products together.
- **Not accounting for conversion costs** (tariffs, fees) when trading cross-exchange products.
- **Submitting too late** → server congestion near deadlines.
- **Trusting Discord strategies** → disinformation is common.
