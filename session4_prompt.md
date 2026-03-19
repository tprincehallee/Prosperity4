# Session 4: Analysis Toolkit, Parameter Optimizer, and Backtester Integration

Read CLAUDE.md first for full competition context.

Do not ask questions — make reasonable decisions and proceed.

## Context

Sessions 1–3 built the complete trading algorithm:
- `trader.py` — full Trader class with 7 strategies: market_make_fixed, market_make_ema, pairs_arb, informed_trader, cross_exchange, circular_arb, options
- `utils/` — math, orderbook, position, and options utilities
- `tests/` — comprehensive test suite
- `scripts/merge_to_submission.py` — submission validator

This session builds the analysis and optimization tooling needed for rapid iteration DURING the competition. These are development-time tools — they are not part of the submission.

---

## Task 1: Round Analysis Notebook Template

Create `analysis/round_analysis_template.py` as a **Python script** (not .ipynb — plain Python is easier for CC to create and for git to diff; the user can convert to a notebook if desired). Use matplotlib for plotting.

The script should be structured as a series of clearly labeled analysis sections that can be run top-to-bottom or cherry-picked. It must work with the CSV format produced by the Prosperity backtester/visualizer.

### 1a: Data loading

```python
# Usage: python analysis/round_analysis_template.py data/round1_day0.csv
```

- Accept a CSV file path as a command-line argument (or default to a glob of `data/*.csv`).
- Prosperity data CSVs typically have columns like: `day`, `timestamp`, `product`, `bid_price_1`, `bid_volume_1`, `ask_price_1`, `ask_volume_1`, `bid_price_2`, etc., `mid_price`, and trade columns.
- Load with pandas. If the exact column format is unknown, make the loader flexible: auto-detect columns, print column names on load, and gracefully skip missing columns.
- Also support a simpler format: just `timestamp`, `product`, `mid_price` columns (for quick manual data).

### 1b: Price series analysis

For each product in the data:
- Plot mid price over time.
- Plot bid-ask spread over time.
- Compute and print: mean, std, min, max, autocorrelation(lag=1), autocorrelation(lag=5).
- Detect regime: is the price stable (std < 1% of mean → likely fixed fair value), trending (autocorr > 0.5), or mean-reverting (autocorr < -0.1)?
- Save plots to `analysis/outputs/price_{product}.png`.

### 1c: Spread and correlation analysis

For all pairs of products:
- Compute rolling correlation (window=50).
- If correlation > 0.7: plot the spread and its z-score, flag as a potential pairs trade.
- For known basket relationships (detect if column names match patterns like PICNIC_BASKET, CROISSANTS, etc.): compute basket NAV and plot basket-NAV spread.
- Save plots to `analysis/outputs/`.

### 1d: Bot behavior analysis

If trade data is available (columns containing `buyer`, `seller`):
- For each unique trader ID: compute total volume, net direction (net buyer or seller), and which products they trade.
- Plot a heatmap: trader ID × product, colored by net volume.
- Flag any trader whose net direction is consistently one-sided (potential informed trader).
- Save to `analysis/outputs/bot_analysis.png`.

### 1e: Volatility analysis

For each product:
- Compute rolling volatility (std of returns, window=20).
- Plot volatility over time.
- If the product looks like an option (name contains "VOUCHER" or similar): compute implied vol from BS using the underlying (if identifiable from naming conventions) and plot IV over time.
- Save to `analysis/outputs/volatility_{product}.png`.

### 1f: Summary report

Print a text summary to stdout:
```
=== Round Analysis Summary ===
Product: RAINFOREST_RESIN
  Type: Fixed fair value (~10000)
  Spread: 2.3 avg
  Suggested strategy: market_make_fixed

Product: KELP
  Type: Random walk
  Spread: 4.1 avg
  Autocorrelation: 0.02
  Suggested strategy: market_make_ema

Product: PICNIC_BASKET1
  Type: ETF (correlated with CROISSANTS r=0.95, JAMS r=0.88)
  Spread vs NAV: z-score range [-3.2, 2.8]
  Suggested strategy: pairs_arb
...
```

Ensure all plots are saved to `analysis/outputs/` (create directory if needed). Use `matplotlib.use('Agg')` at the top so it works headless.

---

## Task 2: Parameter Optimizer

Create `scripts/optimize_params.py` — a grid search tool that finds optimal strategy parameters.

### How it works:

1. Define a parameter grid for a given strategy+product (e.g., spread=[1,2,3,4], ema_alpha=[0.1,0.2,0.3,0.5], skew_factor=[0.5,1.0,1.5]).
2. For each parameter combination: modify PRODUCT_CONFIG in trader.py (or a copy), run the backtester, parse PnL from the output.
3. Record all results in a DataFrame.
4. Generate a parameter landscape heatmap for the top 2 parameters (by PnL sensitivity).
5. Identify the "robustness zone": the region where PnL is within 90% of the maximum over a contiguous area (flat plateau = good; sharp peak = overfit).

### Requirements:

- Accept command-line args: `--product`, `--strategy`, `--param "name=val1,val2,val3"` (repeatable), `--round`, `--days`.
- The optimizer should work by:
  1. Creating a temporary copy of trader.py
  2. Injecting the parameter combination into PRODUCT_CONFIG via string replacement or AST manipulation
  3. Running `prosperity3bt <temp_trader.py> <round>` (or `prosperity4bt` if available) as a subprocess
  4. Parsing PnL from stdout (the backtester prints final PnL)
  5. Collecting results
- If the backtester is not installed, fall back to a simulated backtest using the mock infrastructure from tests/helpers.py (run the Trader against synthetic TradingState sequences and measure PnL).
- Output a CSV of results to `analysis/outputs/param_search_{product}.csv`.
- Generate a matplotlib heatmap of the top 2 parameter dimensions vs PnL. Save to `analysis/outputs/param_landscape_{product}.png`.

### Example usage:
```bash
python scripts/optimize_params.py \
  --product RAINFOREST_RESIN \
  --strategy market_make_fixed \
  --param "spread=1,2,3,4,5" \
  --param "skew_factor=0.5,1.0,1.5,2.0" \
  --round 0
```

---

## Task 3: Backtester Integration Script

Create `scripts/run_backtest.sh` — a convenience wrapper for running backtests.

```bash
#!/bin/bash
# Usage: ./scripts/run_backtest.sh [round] [day]
# Defaults to round 0, all days
# Runs the submission checker first, then the backtester

set -e

ROUND=${1:-0}
DAY=${2:-""}

echo "=== Pre-submission check ==="
python scripts/merge_to_submission.py

echo ""
echo "=== Running backtest: round $ROUND ==="

# Try prosperity4bt first, fall back to prosperity3bt
if command -v prosperity4bt &> /dev/null; then
    BT="prosperity4bt"
elif command -v prosperity3bt &> /dev/null; then
    BT="prosperity3bt"
else
    echo "ERROR: No backtester found. Install with: pip install -U prosperity3bt"
    exit 1
fi

if [ -z "$DAY" ]; then
    $BT trader.py $ROUND
else
    $BT trader.py $ROUND --day $DAY
fi
```

Make it executable: `chmod +x scripts/run_backtest.sh`.

Also create `scripts/run_backtest_all.sh` that runs all available rounds (0 through 5) and summarizes PnL per round:

```bash
#!/bin/bash
# Run backtests across all rounds and summarize results
set -e

python scripts/merge_to_submission.py

# Try to detect backtester
if command -v prosperity4bt &> /dev/null; then
    BT="prosperity4bt"
elif command -v prosperity3bt &> /dev/null; then
    BT="prosperity3bt"
else
    echo "ERROR: No backtester found."
    exit 1
fi

echo "=== Running all rounds ==="
for round in 0 1 2 3 4 5; do
    echo "--- Round $round ---"
    $BT trader.py $round 2>/dev/null || echo "  (no data for round $round)"
    echo ""
done
```

---

## Task 4: Quick-Start Configuration Templates

Create `configs/` directory with ready-to-paste PRODUCT_CONFIG blocks for known Prosperity 3 product sets, so that when P4 products are revealed, we can quickly adapt:

### configs/prosperity3_round1.py
```python
"""
P3 Round 1 product config — Rainforest Resin, Kelp, Squid Ink.
Copy the PRODUCT_CONFIG dict into trader.py when testing against P3 round 1 data.
"""
PRODUCT_CONFIG = {
    "RAINFOREST_RESIN": {
        "strategy": "market_make_fixed",
        "position_limit": 50,
        "fair_value": 10000,
        "spread": 2,
        "skew_factor": 1.0,
    },
    "KELP": {
        "strategy": "market_make_ema",
        "position_limit": 50,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 1.0,
    },
    "SQUID_INK": {
        "strategy": "market_make_ema",
        "position_limit": 50,
        "ema_alpha": 0.2,
        "spread": 3,
        "skew_factor": 1.0,
    },
}
```

### configs/prosperity3_round2.py
```python
"""P3 Round 2 — adds Croissants, Jams, Djembes, Picnic Baskets."""
PRODUCT_CONFIG = {
    # ... round 1 products ...
    "CROISSANTS": {
        "strategy": "market_make_ema",
        "position_limit": 250,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "JAMS": {
        "strategy": "market_make_ema",
        "position_limit": 350,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "DJEMBES": {
        "strategy": "market_make_ema",
        "position_limit": 60,
        "ema_alpha": 0.3,
        "spread": 2,
        "skew_factor": 0.8,
    },
    "PICNIC_BASKET1": {
        "strategy": "pairs_arb",
        "position_limit": 60,
        "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 10,
    },
    "PICNIC_BASKET2": {
        "strategy": "pairs_arb",
        "position_limit": 100,
        "components": {"CROISSANTS": 4, "JAMS": 2},
        "z_entry": 2.0,
        "z_exit": 0.5,
        "spread_window": 50,
        "max_order_size": 15,
    },
}
```

### configs/prosperity3_round4.py
```python
"""P3 Round 4 — adds Volcanic Rock and Vouchers (options)."""
PRODUCT_CONFIG = {
    # ... previous round products ...
    "VOLCANIC_ROCK": {
        "strategy": "market_make_ema",
        "position_limit": 400,
        "ema_alpha": 0.2,
        "spread": 3,
        "skew_factor": 0.5,
    },
    "VOLCANIC_ROCK_VOUCHER_9500": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 9500,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
    },
    "VOLCANIC_ROCK_VOUCHER_9750": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 9750,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
    },
    "VOLCANIC_ROCK_VOUCHER_10000": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10000,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
    },
    "VOLCANIC_ROCK_VOUCHER_10250": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10250,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
    },
    "VOLCANIC_ROCK_VOUCHER_10500": {
        "strategy": "options",
        "position_limit": 200,
        "underlying": "VOLCANIC_ROCK",
        "strike": 10500,
        "expiry_days": 7,
        "risk_free_rate": 0.0,
        "iv_window": 20,
        "iv_z_entry": 1.5,
        "iv_z_exit": 0.5,
        "delta_hedge": True,
    },
}
```

### configs/prosperity3_round5.py
```python
"""P3 Round 5 — adds Macarons (cross-exchange) + trader identity data (Olivia)."""
PRODUCT_CONFIG = {
    # ... previous round products ...
    "MAGNIFICENT_MACARONS": {
        "strategy": "cross_exchange",
        "position_limit": 75,
        "conversion_product": "MAGNIFICENT_MACARONS",
        "storage_cost": 0.1,
        "spread_buffer": 1.0,
        "max_conversion": 10,
    },
    # Override SQUID_INK to use informed trader detection once bot IDs are known:
    # "SQUID_INK": {
    #     "strategy": "informed_trader",
    #     "position_limit": 50,
    #     "tracked_traders": ["Olivia"],
    #     "flow_window": 10,
    #     "signal_threshold": 5,
    #     "base_spread": 2,
    #     "ema_alpha": 0.3,
    # },
}
```

For each config file, include the full merged config from all previous rounds (not just the new products). The user should be able to copy-paste any single config file into trader.py to test against that round's data.

---

## Task 5: Update README.md

Create a `README.md` at the repo root:

```markdown
# Prosperity 4 Trading Toolkit

Tools and strategies for IMC Prosperity 4 (April 2026).

## Quick Start

# Run backtester on round 0
./scripts/run_backtest.sh 0

# Run all tests
python -m pytest tests/ -v

# Validate submission
python scripts/merge_to_submission.py

# Analyze round data
python analysis/round_analysis_template.py data/round1_day0.csv

# Optimize parameters
python scripts/optimize_params.py --product RAINFOREST_RESIN --strategy market_make_fixed --param "spread=1,2,3,4" --round 0

## Architecture

[brief description of the codebase architecture, strategy dispatch, and how to add a new strategy]

## Strategies

[table of all 7 strategies with one-line descriptions]

## Adding a New Product

1. Identify the product archetype (see CLAUDE.md)
2. Add an entry to PRODUCT_CONFIG in trader.py
3. Backtest: ./scripts/run_backtest.sh <round>
4. Optimize: python scripts/optimize_params.py ...
5. Submit: python scripts/merge_to_submission.py
```

Flesh out the README with real content — don't leave placeholders. Make it genuinely useful as a quick-reference during the competition.

---

## Deliverables

1. All tests still pass: `python -m pytest tests/ -v`
2. Submission check passes: `python scripts/merge_to_submission.py`
3. Analysis script runs without error on synthetic data: `python analysis/round_analysis_template.py` (generate a small synthetic CSV if no real data is available, just to prove the script works)
4. Parameter optimizer runs: `python scripts/optimize_params.py --help` prints usage
5. All config files are valid Python: `python -c "exec(open('configs/prosperity3_round1.py').read()); print('OK')"` for each
6. Commit: `git add -A && git commit -m "Session 4: analysis toolkit, param optimizer, configs, README"`
