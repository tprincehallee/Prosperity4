"""
Parameter Optimizer for IMC Prosperity 4

Runs a grid search over strategy parameters, either using the backtester
(prosperity3bt/prosperity4bt) or a simulated backtest with synthetic data.

Usage:
    python scripts/optimize_params.py \\
        --product RAINFOREST_RESIN \\
        --strategy market_make_fixed \\
        --param "spread=1,2,3,4,5" \\
        --param "skew_factor=0.5,1.0,1.5,2.0" \\
        --round 0
"""

import argparse
import csv
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

matplotlib_available = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib_available = True
except ImportError:
    pass


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "analysis", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TRADER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "trader.py")


# ---------------------------------------------------------------------------
# Backtester integration
# ---------------------------------------------------------------------------

def find_backtester():
    """Return the backtester command name, or None if not found."""
    for bt in ("prosperity4bt", "prosperity3bt"):
        if shutil.which(bt):
            return bt
    return None


def run_with_backtester(trader_path, round_num, day=None, timeout=120):
    """
    Run the backtester and parse the PnL from its output.
    Returns float PnL or None on failure.
    """
    bt = find_backtester()
    if bt is None:
        return None

    cmd = [bt, trader_path, str(round_num)]
    if day is not None:
        cmd += ["--day", str(day)]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        return parse_pnl(output)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def parse_pnl(output):
    """
    Extract total PnL from backtester output.
    Handles various output formats prosperity3bt uses.
    """
    # Try common patterns:
    # "Total profit: 12345.67"
    # "Profit: 12345.67"
    # "PnL: 12345.67"
    patterns = [
        r"[Tt]otal\s+[Pp][Nn][Ll]\s*[:=]\s*([-\d.,]+)",
        r"[Tt]otal\s+[Pp]rofit\s*[:=]\s*([-\d.,]+)",
        r"[Pp]rofit\s*[:=]\s*([-\d.,]+)",
        r"[Pp][Nn][Ll]\s*[:=]\s*([-\d.,]+)",
        r"Final\s+PnL\s*[:=]\s*([-\d.,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, output)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    # Last line fallback: if it's just a number
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        try:
            return float(line)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Simulated backtest fallback
# ---------------------------------------------------------------------------

def simulate_backtest(product, strategy, params, num_steps=200):
    """
    Simulated backtest using the Trader class directly against synthetic data.
    Returns estimated PnL (rough heuristic — good enough for relative ranking).
    """
    from tests.helpers import make_order_depth, make_state, run_trader
    import random
    import math
    rng = random.Random(42)

    # Build product config with these params
    config = {"strategy": strategy, "position_limit": 50}
    config.update(params)

    product_config = {product: config}

    # Generate a synthetic price series appropriate for the strategy
    price = 10000.0
    pnl = 0.0
    position = 0
    pos_limit = 50
    trader_data = ""

    for step in range(num_steps):
        # Simple price model
        if strategy == "market_make_fixed":
            noise = rng.randint(-2, 2)
            price = config.get("fair_value", 10000) + noise
        else:
            price += rng.gauss(0, 3)

        spread = rng.uniform(1, 4)
        bid = int(price - spread / 2)
        ask = int(price + spread / 2)
        if bid >= ask:
            bid = int(price) - 1
            ask = int(price) + 1

        od = make_order_depth({bid: 10}, {ask: 10})
        state = make_state(
            order_depths={product: od},
            position={product: position},
            trader_data=trader_data,
            timestamp=step * 100,
        )

        result, _, trader_data = run_trader(state, product_config)

        orders = result.get(product, [])
        for order in orders:
            if order.quantity > 0 and order.price >= ask:
                # Buy filled at ask
                fill_qty = min(order.quantity, 10, pos_limit - position)
                if fill_qty > 0:
                    pnl -= fill_qty * ask
                    position += fill_qty
            elif order.quantity < 0 and order.price <= bid:
                # Sell filled at bid
                fill_qty = min(abs(order.quantity), 10, pos_limit + position)
                if fill_qty > 0:
                    pnl += fill_qty * bid
                    position -= fill_qty

    # Mark-to-market at the end
    pnl += position * price
    return pnl


# ---------------------------------------------------------------------------
# Parameter injection
# ---------------------------------------------------------------------------

def inject_params_into_trader(product, strategy, params, src_path):
    """
    Create a temp copy of trader.py with PRODUCT_CONFIG updated for this product.
    Returns the temp file path.
    """
    with open(src_path) as f:
        code = f.read()

    config_entry = json.dumps({
        product: {"strategy": strategy, "position_limit": 50, **params}
    }, indent=4)

    # Replace the PRODUCT_CONFIG definition
    new_config = f"PRODUCT_CONFIG = {config_entry}\n"
    code_new = re.sub(
        r"^PRODUCT_CONFIG\s*=\s*\{[^}]*\}",
        new_config,
        code,
        flags=re.MULTILINE | re.DOTALL,
    )
    if code_new == code:
        # Fallback: append override after the config block
        code_new = code + f"\n\n# Parameter injection\n{new_config}\n"

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="trader_opt_"
    )
    tmp.write(code_new)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------

def grid_search(product, strategy, param_grid, round_num, day, use_bt):
    """
    Run grid search over all parameter combinations.
    Returns list of {param: value, ..., "pnl": float} dicts.
    """
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    all_combos = list(itertools.product(*param_values))

    total = len(all_combos)
    print(f"\nGrid search: {total} combinations for {product} / {strategy}")
    print(f"Parameters: {param_names}")

    results = []
    bt_available = find_backtester() is not None

    for i, combo in enumerate(all_combos):
        params = dict(zip(param_names, combo))
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"  [{i+1}/{total}] {param_str} ...", end=" ", flush=True)

        if use_bt and bt_available:
            tmp_path = inject_params_into_trader(product, strategy, params, TRADER_PATH)
            try:
                pnl = run_with_backtester(tmp_path, round_num, day)
            finally:
                os.unlink(tmp_path)
            if pnl is None:
                print("FAILED (backtester error)")
                pnl = float("nan")
        else:
            pnl = simulate_backtest(product, strategy, params)

        print(f"PnL = {pnl:.1f}")
        row = dict(params)
        row["pnl"] = pnl
        results.append(row)

    return results, param_names


# ---------------------------------------------------------------------------
# Output: CSV and heatmap
# ---------------------------------------------------------------------------

def save_csv(results, product):
    out = os.path.join(OUTPUT_DIR, f"param_search_{product}.csv")
    if not results:
        return
    fieldnames = list(results[0].keys())
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults saved to: {out}")
    return out


def find_robustness_zone(pnl_values, threshold=0.9):
    """
    Identify the 'robustness zone': indices where PnL >= threshold * max_pnl.
    A wide zone = robust parameters. A single peak = fragile/overfit.
    """
    max_pnl = max(pnl_values)
    if max_pnl <= 0:
        return []
    cutoff = threshold * max_pnl
    return [i for i, v in enumerate(pnl_values) if v >= cutoff]


def plot_heatmap(results, param_names, product):
    """Generate a heatmap of the top 2 parameters vs PnL."""
    if not matplotlib_available:
        print("matplotlib not available — skipping heatmap")
        return
    if len(param_names) < 2:
        # 1D plot
        param = param_names[0]
        xs = [r[param] for r in results]
        ys = [r["pnl"] for r in results]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(xs, ys, "o-")
        ax.set_xlabel(param)
        ax.set_ylabel("PnL")
        ax.set_title(f"Parameter Landscape: {product}")
        # Robustness zone
        robust = find_robustness_zone(ys)
        if robust:
            rx = [xs[i] for i in robust]
            ry = [ys[i] for i in robust]
            ax.fill_between(rx, min(ys), ry, alpha=0.2, color="green",
                            label="Robustness zone (90%)")
            ax.legend()
        plt.tight_layout()
    else:
        # 2D heatmap for first two parameters
        px, py = param_names[0], param_names[1]
        xs = sorted(set(r[px] for r in results))
        ys = sorted(set(r[py] for r in results))
        pnl_grid = [[float("nan")] * len(ys) for _ in range(len(xs))]
        xi_map = {v: i for i, v in enumerate(xs)}
        yi_map = {v: i for i, v in enumerate(ys)}
        for r in results:
            xi = xi_map[r[px]]
            yi = yi_map[r[py]]
            pnl_grid[xi][yi] = r["pnl"]

        fig, ax = plt.subplots(figsize=(8, 6))
        import numpy as np
        arr = [[pnl_grid[i][j] for j in range(len(ys))] for i in range(len(xs))]
        im = ax.imshow(arr, aspect="auto", origin="lower",
                       extent=[0, len(ys), 0, len(xs)])
        ax.set_xticks(range(len(ys)))
        ax.set_xticklabels([str(v) for v in ys])
        ax.set_yticks(range(len(xs)))
        ax.set_yticklabels([str(v) for v in xs])
        ax.set_xlabel(py)
        ax.set_ylabel(px)
        ax.set_title(f"Parameter Landscape: {product}\n(color = PnL)")
        plt.colorbar(im, ax=ax, label="PnL")
        plt.tight_layout()

    out = os.path.join(OUTPUT_DIR, f"param_landscape_{product}.png")
    plt.savefig(out, dpi=100)
    plt.close()
    print(f"Heatmap saved to: {out}")


def print_results_table(results, param_names, top_n=10):
    """Print top N results sorted by PnL."""
    sorted_results = sorted(
        [r for r in results if not (r["pnl"] != r["pnl"])],  # exclude nan
        key=lambda r: r["pnl"],
        reverse=True,
    )
    print(f"\n=== Top {min(top_n, len(sorted_results))} Results ===")
    header = param_names + ["pnl"]
    print("  " + " | ".join(f"{h:>12}" for h in header))
    print("  " + "-" * (15 * len(header)))
    for r in sorted_results[:top_n]:
        vals = [str(r[p]) for p in param_names] + [f"{r['pnl']:.1f}"]
        print("  " + " | ".join(f"{v:>12}" for v in vals))

    if sorted_results:
        best = sorted_results[0]
        print(f"\nBest parameters: {', '.join(f'{p}={best[p]}' for p in param_names)}")
        print(f"Best PnL: {best['pnl']:.1f}")

        pnl_values = [r["pnl"] for r in sorted_results]
        robust = find_robustness_zone(pnl_values)
        print(f"Robustness zone (90% of max): {len(robust)}/{len(pnl_values)} combinations")
        if len(robust) < 3:
            print("WARNING: Sharp peak detected — parameters may be overfit!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_param_arg(s):
    """Parse '--param name=val1,val2,val3' into (name, [val1, val2, val3])."""
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"Invalid --param format: {s!r}. Use name=v1,v2,v3")
    name, vals_str = s.split("=", 1)
    vals = []
    for v in vals_str.split(","):
        v = v.strip()
        try:
            vals.append(int(v))
        except ValueError:
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(v)
    return name.strip(), vals


def main():
    parser = argparse.ArgumentParser(
        description="Grid search optimizer for IMC Prosperity trading strategies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/optimize_params.py \\
      --product RAINFOREST_RESIN \\
      --strategy market_make_fixed \\
      --param "spread=1,2,3,4,5" \\
      --param "skew_factor=0.5,1.0,1.5,2.0" \\
      --round 0

  python scripts/optimize_params.py \\
      --product KELP \\
      --strategy market_make_ema \\
      --param "ema_alpha=0.1,0.2,0.3,0.5" \\
      --param "spread=1,2,3" \\
      --simulate
""",
    )
    parser.add_argument("--product", required=True, help="Product symbol")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument(
        "--param", action="append", default=[],
        metavar="name=v1,v2,...",
        help="Parameter grid (repeatable). E.g. --param spread=1,2,3",
    )
    parser.add_argument("--round", type=int, default=0, help="Backtest round number")
    parser.add_argument("--day", type=int, default=None, help="Specific day (optional)")
    parser.add_argument(
        "--simulate", action="store_true",
        help="Force simulated backtest even if backtester is available",
    )
    parser.add_argument("--top", type=int, default=10, help="Show top N results")

    args = parser.parse_args()

    # Parse parameter grid
    param_grid = {}
    for p in args.param:
        name, vals = parse_param_arg(p)
        param_grid[name] = vals

    if not param_grid:
        print("WARNING: No --param arguments given. Running with empty grid (single eval).")
        param_grid = {"__dummy__": [1]}

    use_bt = not args.simulate
    if use_bt and find_backtester() is None:
        print("No backtester found (install: pip install -U prosperity3bt). Using simulation.")
        use_bt = False

    results, param_names = grid_search(
        args.product, args.strategy, param_grid, args.round, args.day, use_bt
    )

    if "__dummy__" in param_names:
        param_names.remove("__dummy__")
        for r in results:
            r.pop("__dummy__", None)

    print_results_table(results, param_names, args.top)
    save_csv(results, args.product)
    if param_names:
        plot_heatmap(results, param_names, args.product)


if __name__ == "__main__":
    main()
