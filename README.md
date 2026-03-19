# Prosperity 4 Trading Toolkit

Algorithmic trading strategies and analysis tools for **IMC Prosperity 4** (April 2026).
The competition runs for 15 days across 5 rounds; the goal is to maximize PnL (SeaShells)
by submitting a single Python trading algorithm.

---

## Quick Start

```bash
# Run all tests
python -m pytest tests/ -v

# Validate and build submission
python scripts/merge_to_submission.py

# Run backtester on round 0 (requires: pip install -U prosperity3bt)
./scripts/run_backtest.sh 0

# Run all rounds
./scripts/run_backtest_all.sh

# Analyze round data (auto-generates synthetic data if none present)
python analysis/round_analysis_template.py data/round1_day0.csv

# Optimize parameters (simulated backtest — no backtester needed)
python scripts/optimize_params.py \
    --product RAINFOREST_RESIN \
    --strategy market_make_fixed \
    --param "spread=1,2,3,4" \
    --param "skew_factor=0.5,1.0,1.5" \
    --simulate
```

---

## Architecture

```
Prosperity4/
├── trader.py                    # Submission file — single-file Trader class
├── strategies/                  # Modular strategy implementations
├── utils/                       # Math, orderbook, position, options utilities
├── analysis/                    # Round analysis scripts
│   └── round_analysis_template.py
├── configs/                     # Ready-to-use PRODUCT_CONFIG blocks per round
├── tests/                       # Full pytest test suite
├── scripts/
│   ├── merge_to_submission.py   # Validate + build submission/trader.py
│   ├── optimize_params.py       # Grid search parameter optimizer
│   ├── run_backtest.sh          # Single-round backtest runner
│   └── run_backtest_all.sh      # All-rounds backtest runner
└── data/                        # Round CSV data (not committed)
```

### How the Algorithm Works

1. Each timestep, `Trader.run(state)` is called with the full market snapshot.
2. `traderData` (a JSON string) is deserialized to restore rolling state from the previous timestep.
3. For each product in `PRODUCT_CONFIG`, the matching `strategy_<name>` method is called.
4. Strategy methods return a list of `Order` objects. Orders are clipped to position limits before being returned.
5. Special mechanisms:
   - **Pairs arb** component orders are accumulated in `_component_orders` and merged into `result` after the main loop.
   - **Options delta hedge** orders are written to `_hedge_orders` and merged similarly.
6. State is serialized back to `traderData` and returned with orders.

### Adding a New Strategy

1. Add a `strategy_<name>` method to the `Trader` class in `trader.py`.
2. Add a `PRODUCT_CONFIG` entry with `"strategy": "<name>"`.
3. Write tests in `tests/test_all_strategies.py`.
4. Backtest and optimize.

---

## Strategies

| Strategy | Method | When to Use |
|---|---|---|
| **market_make_fixed** | `strategy_market_make_fixed` | Product with a known constant fair value (e.g. Rainforest Resin). Quotes bid/ask around fair_value, takes mispriced orders, skews inventory. |
| **market_make_ema** | `strategy_market_make_ema` | Random-walk product with no known fair value (e.g. Kelp). Uses EMA of mid prices as fair value estimate. |
| **pairs_arb** | `strategy_pairs_arb` | ETF/basket products whose NAV can be computed from component prices (e.g. Picnic Baskets). Trades z-score of basket-NAV spread. |
| **informed_trader** | `strategy_informed_trader` | Products where a specific bot trades with predictive information (e.g. "Olivia" in P3). Aggregates bot net flow as a directional signal. |
| **cross_exchange** | `strategy_cross_exchange` | Products tradeable locally AND on a foreign exchange via the conversion mechanism (e.g. Magnificent Macarons). Exploits price gaps between exchanges. |
| **circular_arb** | `strategy_circular_arb` | Products forming a cycle of exchange rates. Detects when round-trip product of rates deviates from 1.0 beyond a threshold. |
| **options** | `strategy_options` | Call options with a known underlying (e.g. Volcanic Rock Vouchers). Black-Scholes pricing, implied vol mean reversion, optional delta hedging. |

---

## Adding a New Product (Round Workflow)

When a new round starts:

1. **Download data** from the Prosperity dashboard immediately.
2. **Classify the product**:
   ```bash
   python analysis/round_analysis_template.py data/round<N>_day0.csv
   ```
   The script detects price regime (fixed/random walk/trending), prints correlation analysis,
   flags potential informed traders from `market_trades`, and suggests a strategy.
3. **Pick a config template** from `configs/` as a starting point.
4. **Add to `PRODUCT_CONFIG`** in `trader.py`:
   ```python
   "NEW_PRODUCT": {
       "strategy": "market_make_ema",
       "position_limit": 50,
       "ema_alpha": 0.3,
       "spread": 2,
   },
   ```
5. **Run tests** — make sure nothing is broken:
   ```bash
   python -m pytest tests/ -v
   ```
6. **Submit early** with `python scripts/merge_to_submission.py`, then iterate.
7. **Optimize parameters**:
   ```bash
   python scripts/optimize_params.py \
       --product NEW_PRODUCT --strategy market_make_ema \
       --param "ema_alpha=0.1,0.2,0.3,0.5" --param "spread=1,2,3,4"
   ```
   Look for a **flat robustness zone** — avoid sharp-peak parameters (overfit).
8. **Check live results** from the submission dashboard and adjust.

---

## Configuration Templates

Ready-to-paste `PRODUCT_CONFIG` blocks for all Prosperity 3 rounds are in `configs/`:

| File | Products |
|---|---|
| `configs/prosperity3_round1.py` | RAINFOREST_RESIN, KELP, SQUID_INK |
| `configs/prosperity3_round2.py` | + CROISSANTS, JAMS, DJEMBES, PICNIC_BASKET1/2 |
| `configs/prosperity3_round4.py` | + VOLCANIC_ROCK, VOLCANIC_ROCK_VOUCHER_* (5 strikes) |
| `configs/prosperity3_round5.py` | + MAGNIFICENT_MACARONS (cross-exchange) |

---

## Key Principles (from Top-Team Analysis)

- **Robustness over complexity**: pick parameters from flat performance plateaus, not sharp peaks.
- **Submit early each round**: the submission system can be slow near deadlines.
- **Every product matters**: even small edges compound across 15 days.
- **Watch `market_trades`**: the most alpha-generating insight in P3 was tracking an informed bot's net flow.
- **Discord disinformation is real**: validate strategies with your own backtests, not community posts.
- **Manual challenges**: budget 2–3 hours per round for the standalone math puzzles — high leverage.

---

## Dependencies

```bash
pip install pytest matplotlib pandas
pip install -U prosperity3bt   # backtester (use prosperity4bt when available)
```

The submission itself (`trader.py`) requires only the standard library (`math`, `json`, `collections`)
plus `datamodel` (provided by the competition platform).
