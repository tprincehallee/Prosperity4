"""
Round Analysis Template for IMC Prosperity 4

Usage:
    python analysis/round_analysis_template.py [data_file.csv]

If no file is given, looks for data/*.csv. If data/ is empty, generates
synthetic data to demonstrate all analysis sections.

Output plots are saved to analysis/outputs/.
"""

import sys
import os
import math
import glob
import argparse
import csv
from collections import defaultdict

matplotlib_available = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    matplotlib_available = True
except ImportError:
    print("WARNING: matplotlib not available. Plots will be skipped.")

pandas_available = False
try:
    import pandas as pd
    pandas_available = True
except ImportError:
    print("WARNING: pandas not available. Using fallback CSV reader.")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv(filepath):
    """
    Load a Prosperity data CSV. Flexible: handles both the full backtester
    format and a minimal timestamp/product/mid_price format.

    Returns a dict: {product: [{col: val, ...}, ...]}
    """
    print(f"Loading: {filepath}")
    rows = []
    with open(filepath, newline="") as f:
        # Detect delimiter (semicolons common in Prosperity CSVs)
        sample = f.read(2048)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        cols = reader.fieldnames or []
        print(f"  Columns: {cols}")
        for row in reader:
            rows.append(row)

    print(f"  Rows loaded: {len(rows)}")
    if not rows:
        return {}

    # Parse numeric fields
    numeric_keys = [
        "timestamp", "day", "mid_price",
        "bid_price_1", "bid_volume_1", "ask_price_1", "ask_volume_1",
        "bid_price_2", "bid_volume_2", "ask_price_2", "ask_volume_2",
        "bid_price_3", "bid_volume_3", "ask_price_3", "ask_volume_3",
        "price", "quantity",
    ]
    parsed = []
    for row in rows:
        r = dict(row)
        for k in numeric_keys:
            if k in r:
                try:
                    r[k] = float(r[k])
                except (ValueError, TypeError):
                    r[k] = None
        parsed.append(r)

    # Group by product
    product_col = "product" if "product" in (parsed[0] or {}) else None
    if product_col is None:
        # Single-product file: treat as one unnamed product
        return {"PRODUCT": parsed}

    by_product = defaultdict(list)
    for row in parsed:
        prod = row.get("product", "UNKNOWN")
        by_product[prod].append(row)
    return dict(by_product)


def generate_synthetic_data():
    """
    Generate synthetic market data for demonstration when no real data exists.
    Returns the same format as load_csv.
    """
    print("No data file found. Generating synthetic data for demonstration.")
    import random
    random.seed(42)
    data = {}

    # Product 1: Fixed fair value (like Rainforest Resin)
    rows = []
    price = 10000
    for t in range(0, 10000, 100):
        noise = random.randint(-2, 2)
        mid = price + noise
        rows.append({
            "timestamp": float(t), "product": "RAINFOREST_RESIN",
            "mid_price": float(mid),
            "bid_price_1": float(mid - 1), "bid_volume_1": 10.0,
            "ask_price_1": float(mid + 1), "ask_volume_1": 10.0,
        })
    data["RAINFOREST_RESIN"] = rows

    # Product 2: Random walk (like Kelp)
    rows = []
    price = 2000.0
    for t in range(0, 10000, 100):
        price += random.gauss(0, 3)
        spread = random.uniform(1, 4)
        rows.append({
            "timestamp": float(t), "product": "KELP",
            "mid_price": price,
            "bid_price_1": price - spread / 2, "bid_volume_1": 8.0,
            "ask_price_1": price + spread / 2, "ask_volume_1": 8.0,
        })
    data["KELP"] = rows

    # Product 3: Basket (correlated with KELP)
    basket_rows = []
    comp_rows = []
    kelp_prices = [r["mid_price"] for r in data["KELP"]]
    for i, t in enumerate(range(0, 10000, 100)):
        comp_mid = kelp_prices[i] * 0.5 + 200
        nav = comp_mid * 2
        basket_mid = nav + random.gauss(0, 5)  # trades at NAV ± noise
        basket_rows.append({
            "timestamp": float(t), "product": "PICNIC_BASKET1",
            "mid_price": basket_mid,
            "bid_price_1": basket_mid - 2, "bid_volume_1": 5.0,
            "ask_price_1": basket_mid + 2, "ask_volume_1": 5.0,
        })
        comp_rows.append({
            "timestamp": float(t), "product": "CROISSANTS",
            "mid_price": comp_mid,
            "bid_price_1": comp_mid - 1, "bid_volume_1": 20.0,
            "ask_price_1": comp_mid + 1, "ask_volume_1": 20.0,
        })
    data["PICNIC_BASKET1"] = basket_rows
    data["CROISSANTS"] = comp_rows

    # Product 4: Option (voucher)
    rock_price = 10000.0
    rock_rows = []
    voucher_rows = []
    for t in range(0, 10000, 100):
        rock_price += random.gauss(0, 10)
        sigma = 0.2 + random.gauss(0, 0.02)
        T = max(0.001, 5 / 252.0 - t / (252 * 86400))
        # Simple intrinsic approximation
        intrinsic = max(0.0, rock_price - 10000)
        time_val = rock_price * sigma * math.sqrt(T) * 0.4  # rough approx
        opt_price = intrinsic + time_val
        rock_rows.append({
            "timestamp": float(t), "product": "VOLCANIC_ROCK",
            "mid_price": rock_price,
            "bid_price_1": rock_price - 3, "bid_volume_1": 20.0,
            "ask_price_1": rock_price + 3, "ask_volume_1": 20.0,
        })
        voucher_rows.append({
            "timestamp": float(t), "product": "VOLCANIC_ROCK_VOUCHER_10000",
            "mid_price": opt_price,
            "bid_price_1": opt_price - 1, "bid_volume_1": 5.0,
            "ask_price_1": opt_price + 1, "ask_volume_1": 5.0,
        })
    data["VOLCANIC_ROCK"] = rock_rows
    data["VOLCANIC_ROCK_VOUCHER_10000"] = voucher_rows

    return data


def find_data_files():
    """Look for data CSVs in the data/ directory."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = os.path.join(repo_root, "data", "*.csv")
    return glob.glob(pattern)


# ---------------------------------------------------------------------------
# Section 1b: Price series analysis
# ---------------------------------------------------------------------------

def compute_autocorr(values, lag=1):
    """Autocorrelation at given lag using Pearson formula."""
    n = len(values)
    if n <= lag + 1:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values)
    if var == 0:
        return 0.0
    cov = sum((values[i] - mean) * (values[i - lag] - mean) for i in range(lag, n))
    return cov / var


def detect_regime(values, autocorr1):
    """Classify price series regime."""
    if len(values) < 2:
        return "unknown"
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    cv = std / mean if mean != 0 else 0
    if cv < 0.01:
        return "fixed_fair_value"
    elif autocorr1 > 0.5:
        return "trending"
    elif autocorr1 < -0.1:
        return "mean_reverting"
    else:
        return "random_walk"


def analyze_price_series(product, rows, summary):
    """Section 1b: price series plots and stats for one product."""
    timestamps = [r.get("timestamp", i) for i, r in enumerate(rows)]
    mids = [r.get("mid_price") for r in rows]
    mids = [v for v in mids if v is not None]
    if not mids:
        return

    bid1 = [r.get("bid_price_1") for r in rows]
    ask1 = [r.get("ask_price_1") for r in rows]
    spreads = []
    for b, a in zip(bid1, ask1):
        if b is not None and a is not None:
            spreads.append(a - b)

    mean_mid = sum(mids) / len(mids)
    std_mid = (sum((v - mean_mid) ** 2 for v in mids) / len(mids)) ** 0.5
    autocorr1 = compute_autocorr(mids, 1)
    autocorr5 = compute_autocorr(mids, 5)
    regime = detect_regime(mids, autocorr1)

    avg_spread = sum(spreads) / len(spreads) if spreads else float("nan")

    print(f"\n  {product}:")
    print(f"    mean={mean_mid:.2f}, std={std_mid:.2f}, "
          f"min={min(mids):.2f}, max={max(mids):.2f}")
    print(f"    autocorr(1)={autocorr1:.3f}, autocorr(5)={autocorr5:.3f}")
    print(f"    regime={regime}, avg_spread={avg_spread:.2f}")

    summary[product] = {
        "mean": mean_mid, "std": std_mid, "min": min(mids), "max": max(mids),
        "autocorr1": autocorr1, "autocorr5": autocorr5, "regime": regime,
        "avg_spread": avg_spread,
    }

    if not matplotlib_available:
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=False)
    ax1.plot(timestamps[:len(mids)], mids, linewidth=0.8)
    ax1.set_title(f"{product} — Mid Price")
    ax1.set_ylabel("Price")
    ax1.axhline(mean_mid, color="red", linestyle="--", alpha=0.5, label=f"mean={mean_mid:.1f}")
    ax1.legend(fontsize=8)

    if spreads:
        ax2.plot(timestamps[:len(spreads)], spreads, linewidth=0.8, color="orange")
        ax2.set_title(f"{product} — Bid-Ask Spread")
        ax2.set_ylabel("Spread")
        ax2.axhline(avg_spread, color="red", linestyle="--", alpha=0.5,
                    label=f"avg={avg_spread:.2f}")
        ax2.legend(fontsize=8)

    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, f"price_{product}.png")
    plt.savefig(out, dpi=100)
    plt.close()
    print(f"    Saved: {out}")


# ---------------------------------------------------------------------------
# Section 1c: Spread and correlation analysis
# ---------------------------------------------------------------------------

def rolling_correlation(xs, ys, window=50):
    """Compute rolling correlation between two aligned series."""
    n = min(len(xs), len(ys))
    result = [float("nan")] * n
    for i in range(window - 1, n):
        xw = xs[i - window + 1:i + 1]
        yw = ys[i - window + 1:i + 1]
        mx = sum(xw) / window
        my = sum(yw) / window
        num = sum((a - mx) * (b - my) for a, b in zip(xw, yw))
        dx = sum((a - mx) ** 2 for a in xw)
        dy = sum((b - my) ** 2 for b in yw)
        denom = (dx * dy) ** 0.5
        result[i] = num / denom if denom > 0 else 0.0
    return result


def rolling_zscore(values, window=50):
    """Rolling z-score."""
    n = len(values)
    result = [0.0] * n
    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        m = sum(w) / window
        s = (sum((v - m) ** 2 for v in w) / window) ** 0.5
        result[i] = (values[i] - m) / s if s > 0 else 0.0
    return result


BASKET_COMPOSITIONS = {
    "PICNIC_BASKET1": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
    "PICNIC_BASKET2": {"CROISSANTS": 4, "JAMS": 2},
}


def analyze_correlations(by_product, summary):
    """Section 1c: pair correlations and basket-NAV spread."""
    products = list(by_product.keys())
    n = len(products)
    if n < 2:
        return

    # Build aligned mid price series for each product
    def get_mids(rows):
        return [r.get("mid_price") for r in rows if r.get("mid_price") is not None]

    mids = {p: get_mids(rows) for p, rows in by_product.items()}

    # Pairwise correlation
    pairs_flagged = []
    for i in range(n):
        for j in range(i + 1, n):
            pa, pb = products[i], products[j]
            xa, xb = mids[pa], mids[pb]
            min_len = min(len(xa), len(xb))
            if min_len < 10:
                continue
            xa, xb = xa[:min_len], xb[:min_len]
            mx = sum(xa) / min_len
            my = sum(xb) / min_len
            num = sum((a - mx) * (b - my) for a, b in zip(xa, xb))
            dx = sum((a - mx) ** 2 for a in xa) ** 0.5
            dy = sum((b - my) ** 2 for b in xb) ** 0.5
            corr = num / (dx * dy) if dx * dy > 0 else 0.0
            if abs(corr) > 0.7:
                pairs_flagged.append((pa, pb, corr))
                print(f"    High correlation: {pa} vs {pb}: r={corr:.3f} → potential pairs trade")
                summary.setdefault(pa, {})["correlated_with"] = f"{pb} r={corr:.2f}"

    # Basket NAV spread
    for basket, comps in BASKET_COMPOSITIONS.items():
        if basket not in by_product:
            continue
        if not all(c in by_product for c in comps):
            continue
        basket_mids = mids[basket]
        min_len = min(len(basket_mids), *(len(mids[c]) for c in comps))
        navs = []
        for i in range(min_len):
            nav = sum(w * mids[c][i] for c, w in comps.items())
            navs.append(nav)
        spreads = [basket_mids[i] - navs[i] for i in range(min_len)]
        z = rolling_zscore(spreads, 50)
        z_valid = [v for v in z if not math.isnan(v)]
        if z_valid:
            z_range = (min(z_valid), max(z_valid))
            print(f"    {basket} NAV spread z-score range: [{z_range[0]:.2f}, {z_range[1]:.2f}]")
            summary.setdefault(basket, {}).update({
                "type": "ETF",
                "spread_z_range": z_range,
                "suggested_strategy": "pairs_arb",
            })

        if matplotlib_available:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 5))
            ax1.plot(spreads, linewidth=0.8)
            ax1.set_title(f"{basket} — Basket vs NAV Spread")
            ax1.set_ylabel("Spread")
            ax2.plot(z, linewidth=0.8, color="purple")
            ax2.axhline(2.0, color="red", linestyle="--", alpha=0.5)
            ax2.axhline(-2.0, color="green", linestyle="--", alpha=0.5)
            ax2.set_title(f"{basket} — Spread Z-Score")
            ax2.set_ylabel("Z-Score")
            plt.tight_layout()
            out = os.path.join(OUTPUT_DIR, f"basket_spread_{basket}.png")
            plt.savefig(out, dpi=100)
            plt.close()
            print(f"    Saved: {out}")


# ---------------------------------------------------------------------------
# Section 1d: Bot behavior analysis
# ---------------------------------------------------------------------------

def analyze_bots(by_product):
    """Section 1d: detect informed traders from buyer/seller data."""
    has_trader_data = False
    trader_net = defaultdict(lambda: defaultdict(float))  # trader -> product -> net_vol
    trader_vol = defaultdict(lambda: defaultdict(float))

    for product, rows in by_product.items():
        for row in rows:
            buyer = row.get("buyer")
            seller = row.get("seller")
            qty = row.get("quantity", 0) or 0
            if buyer and buyer not in ("", "SUBMISSION"):
                trader_net[buyer][product] += qty
                trader_vol[buyer][product] += abs(qty)
                has_trader_data = True
            if seller and seller not in ("", "SUBMISSION"):
                trader_net[seller][product] -= qty
                trader_vol[seller][product] += abs(qty)
                has_trader_data = True

    if not has_trader_data:
        print("    No trader ID data found in this dataset.")
        return

    traders = list(trader_net.keys())
    products = list(by_product.keys())
    print(f"    Traders found: {traders}")

    for trader in traders:
        nets = trader_net[trader]
        total_net = sum(nets.values())
        total_vol = sum(trader_vol[trader].values())
        direction = "buyer" if total_net > 0 else "seller"
        skew = abs(total_net) / total_vol if total_vol > 0 else 0
        if skew > 0.6:
            print(f"    INFORMED TRADER CANDIDATE: {trader} — {direction}, "
                  f"net={total_net:.0f}, vol={total_vol:.0f}, skew={skew:.2f}")

    if not matplotlib_available:
        return

    # Heatmap: trader x product
    matrix = []
    for trader in traders:
        row = [trader_net[trader].get(p, 0) for p in products]
        matrix.append(row)

    if not matrix or not matrix[0]:
        return

    fig, ax = plt.subplots(figsize=(max(6, len(products) * 1.2), max(4, len(traders) * 0.8)))
    data_arr = matrix
    vmax = max(abs(v) for row in data_arr for v in row) or 1
    im = ax.imshow(data_arr, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(products)))
    ax.set_xticklabels(products, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(traders)))
    ax.set_yticklabels(traders, fontsize=8)
    ax.set_title("Bot Net Volume Heatmap (green=net buyer, red=net seller)")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "bot_analysis.png")
    plt.savefig(out, dpi=100)
    plt.close()
    print(f"    Saved: {out}")


# ---------------------------------------------------------------------------
# Section 1e: Volatility analysis
# ---------------------------------------------------------------------------

def compute_rolling_vol(prices, window=20):
    """Rolling std of log returns."""
    if len(prices) < 2:
        return []
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
        else:
            returns.append(0.0)
    vols = []
    for i in range(window - 1, len(returns)):
        w = returns[i - window + 1:i + 1]
        mean = sum(w) / window
        v = (sum((x - mean) ** 2 for x in w) / window) ** 0.5
        vols.append(v)
    return vols


def analyze_volatility(by_product, summary):
    """Section 1e: rolling vol and implied vol for option-like products."""
    # Map underlying names for vouchers
    underlying_map = {}
    for p in by_product:
        if "VOUCHER" in p or "OPTION" in p:
            # Try to find underlying by stripping voucher suffix
            for candidate in by_product:
                if candidate in p and "VOUCHER" not in candidate and "OPTION" not in candidate:
                    underlying_map[p] = candidate
                    break
            # Also try VOLCANIC_ROCK -> VOLCANIC_ROCK_VOUCHER_*
            if p not in underlying_map:
                for candidate in by_product:
                    if "ROCK" in candidate and "VOUCHER" not in candidate:
                        underlying_map[p] = candidate
                        break

    for product, rows in by_product.items():
        mids = [r.get("mid_price") for r in rows if r.get("mid_price") is not None]
        if not mids:
            continue
        vols = compute_rolling_vol(mids, 20)
        if not vols:
            continue
        avg_vol = sum(vols) / len(vols)
        print(f"    {product}: avg rolling vol = {avg_vol:.4f} ({avg_vol*100:.2f}%/timestep)")

        if not matplotlib_available:
            continue

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(vols, linewidth=0.8, color="steelblue")
        ax.set_title(f"{product} — Rolling Volatility (window=20)")
        ax.set_ylabel("Volatility (log return std)")
        ax.axhline(avg_vol, color="red", linestyle="--", alpha=0.5, label=f"avg={avg_vol:.4f}")
        ax.legend(fontsize=8)
        plt.tight_layout()
        out = os.path.join(OUTPUT_DIR, f"volatility_{product}.png")
        plt.savefig(out, dpi=100)
        plt.close()
        print(f"    Saved: {out}")


# ---------------------------------------------------------------------------
# Section 1f: Summary report
# ---------------------------------------------------------------------------

REGIME_STRATEGY = {
    "fixed_fair_value": "market_make_fixed",
    "random_walk": "market_make_ema",
    "trending": "market_make_ema",
    "mean_reverting": "market_make_ema",
    "unknown": "market_make_ema",
    "ETF": "pairs_arb",
}


def print_summary(by_product, summary):
    """Section 1f: print text summary report."""
    print("\n" + "=" * 60)
    print("=== Round Analysis Summary ===")
    print("=" * 60)

    for product in sorted(by_product.keys()):
        s = summary.get(product, {})
        regime = s.get("regime", "unknown")
        ptype = s.get("type", regime.replace("_", " ").title())

        if "VOUCHER" in product or "OPTION" in product:
            ptype = "Options (call voucher)"
            strategy = "options"
        elif "BASKET" in product:
            ptype = f"ETF (see basket-NAV spread)"
            strategy = "pairs_arb"
        elif "MACARONS" in product:
            ptype = "Cross-exchange arbitrage"
            strategy = "cross_exchange"
        elif regime == "fixed_fair_value":
            ptype = f"Fixed fair value (~{s.get('mean', 0):.0f})"
            strategy = "market_make_fixed"
        else:
            strategy = REGIME_STRATEGY.get(regime, "market_make_ema")

        print(f"\nProduct: {product}")
        print(f"  Type: {ptype}")
        if s.get("avg_spread") is not None and not math.isnan(s.get("avg_spread", float("nan"))):
            print(f"  Spread: {s['avg_spread']:.2f} avg")
        if s.get("autocorr1") is not None:
            print(f"  Autocorrelation: {s['autocorr1']:.3f}")
        if s.get("correlated_with"):
            print(f"  Correlated with: {s['correlated_with']}")
        if s.get("spread_z_range"):
            z = s["spread_z_range"]
            print(f"  Spread vs NAV: z-score range [{z[0]:.2f}, {z[1]:.2f}]")
        print(f"  Suggested strategy: {strategy}")

    print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="IMC Prosperity Round Analysis")
    parser.add_argument("datafile", nargs="?", help="CSV data file to analyze")
    args = parser.parse_args()

    if args.datafile:
        filepath = args.datafile
        if not os.path.exists(filepath):
            print(f"ERROR: File not found: {filepath}")
            sys.exit(1)
        by_product = load_csv(filepath)
    else:
        files = find_data_files()
        if files:
            filepath = files[0]
            print(f"Auto-detected data file: {filepath}")
            by_product = load_csv(filepath)
        else:
            by_product = generate_synthetic_data()

    if not by_product:
        print("ERROR: No data loaded.")
        sys.exit(1)

    print(f"\nProducts found: {list(by_product.keys())}")
    summary = {}

    print("\n--- Section 1b: Price Series Analysis ---")
    for product, rows in sorted(by_product.items()):
        analyze_price_series(product, rows, summary)

    print("\n--- Section 1c: Correlation & Spread Analysis ---")
    analyze_correlations(by_product, summary)

    print("\n--- Section 1d: Bot Behavior Analysis ---")
    analyze_bots(by_product)

    print("\n--- Section 1e: Volatility Analysis ---")
    analyze_volatility(by_product, summary)

    print_summary(by_product, summary)

    print(f"\nAll plots saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
