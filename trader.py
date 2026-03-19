"""
IMC Prosperity 4 — Main Trader Algorithm

This is the submission file. During development, it imports from
strategies/ and utils/. For submission, use merge_to_submission.py
to inline everything into a single file.

Architecture:
    1. run() deserializes traderData -> calls trade_product() per product
    2. trade_product() dispatches to the correct strategy based on product config
    3. Each strategy returns proposed orders
    4. Orders are clipped to position limits
    5. State is serialized back to traderData
"""

from datamodel import (
    Listing,
    Observation,
    Order,
    OrderDepth,
    ProsperityEncoder,
    Symbol,
    Trade,
    TradingState,
)
from typing import Any, Dict, List, Tuple
import json
import math
from collections import deque


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Product -> strategy mapping. Update each round as new products are introduced.
# Strategy names correspond to methods on the Trader class.
PRODUCT_CONFIG: Dict[str, dict] = {
    # Round 0 / Tutorial examples (update with actual P4 products):
    # "RAINFOREST_RESIN": {
    #     "strategy": "market_make_fixed",
    #     "position_limit": 50,
    #     "fair_value": 10000,
    #     "spread": 2,
    # },
    # "KELP": {
    #     "strategy": "market_make_ema",
    #     "position_limit": 50,
    #     "ema_alpha": 0.3,
    #     "spread": 2,
    # },
}


# ---------------------------------------------------------------------------
# Utility functions (inlined for submission; during dev, import from utils/)
# ---------------------------------------------------------------------------

def ema_update(current_ema, new_value, alpha):
    if current_ema is None:
        return new_value
    return alpha * new_value + (1 - alpha) * current_ema


def best_bid(od: OrderDepth):
    return max(od.buy_orders.keys()) if od.buy_orders else None


def best_ask(od: OrderDepth):
    return min(od.sell_orders.keys()) if od.sell_orders else None


def mid_price(od: OrderDepth):
    bb, ba = best_bid(od), best_ask(od)
    if bb is None or ba is None:
        return None
    return (bb + ba) / 2.0


def wall_mid(od: OrderDepth):
    bb, ba = best_bid(od), best_ask(od)
    if bb is None or ba is None:
        return None
    bid_vol = od.buy_orders[bb]
    ask_vol = abs(od.sell_orders[ba])
    total = bid_vol + ask_vol
    if total == 0:
        return (bb + ba) / 2.0
    return (bb * ask_vol + ba * bid_vol) / total


def clip_orders(symbol, orders, current_pos, pos_limit):
    clipped = []
    sim_pos = current_pos
    for order in orders:
        qty = order.quantity
        if qty > 0:
            max_qty = pos_limit - sim_pos
            if max_qty <= 0:
                continue
            clipped_qty = min(qty, max_qty)
        elif qty < 0:
            max_qty = pos_limit + sim_pos
            if max_qty <= 0:
                continue
            clipped_qty = -min(abs(qty), max_qty)
        else:
            continue
        clipped.append(Order(symbol, order.price, clipped_qty))
        sim_pos += clipped_qty
    return clipped


def net_trade_flow(trades, trader_id):
    net = 0
    for t in trades:
        if t.buyer == trader_id:
            net += t.quantity
        if t.seller == trader_id:
            net -= t.quantity
    return net


def rolling_z_score(values: List[float], window: int) -> float:
    """Z-score of the last element relative to the rolling window."""
    if len(values) < 2:
        return 0.0
    windowed = values[-window:] if len(values) >= window else values
    if len(windowed) < 2:
        return 0.0
    mean = sum(windowed) / len(windowed)
    variance = sum((x - mean) ** 2 for x in windowed) / len(windowed)
    if variance == 0:
        return 0.0
    return (windowed[-1] - mean) / math.sqrt(variance)


def norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call option price."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put price via put-call parity: P = C - S + K*e^(-rT)."""
    return bs_call_price(S, K, T, r, sigma) - S + K * math.exp(-r * T)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Call delta: dC/dS = N(d1)."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1)


def implied_vol(
    market_price: float, S: float, K: float, T: float, r: float,
    option_type: str = "call",
) -> float:
    """Solve for implied volatility via bisection. Returns None if no convergence."""
    if T <= 0:
        return None
    lo, hi = 0.01, 5.0
    price_fn = bs_call_price if option_type == "call" else bs_put_price
    for _ in range(50):
        mid = (lo + hi) / 2.0
        price = price_fn(S, K, T, r, mid)
        if abs(price - market_price) < 0.001:
            return mid
        if price > market_price:
            hi = mid
        else:
            lo = mid
    return None


# ---------------------------------------------------------------------------
# Logger (compatible with Prosperity Visualizer)
# ---------------------------------------------------------------------------

class Logger:
    """
    Structured logger that outputs in the format expected by the
    Prosperity Visualizer. Call logger.flush() at the end of run().
    """

    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750  # Character limit for logs

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(
        self,
        state: TradingState,
        orders: dict[Symbol, list[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
        """Print the full log line for the visualizer."""
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )
        # Truncate to fit log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(
                        state, self._truncate(state.traderData, max_item_length)
                    ),
                    self.compress_orders(orders),
                    conversions,
                    self._truncate(trader_data, max_item_length),
                    self._truncate(self.logs, max_item_length),
                ]
            )
        )
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append(
                [listing.symbol, listing.product, listing.denomination]
            )
        return compressed

    def compress_order_depths(
        self, order_depths: dict[Symbol, OrderDepth]
    ) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, od in order_depths.items():
            compressed[symbol] = [od.buy_orders, od.sell_orders]
        return compressed

    def compress_trades(
        self, trades: dict[Symbol, list[Trade]]
    ) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append(
                    [
                        trade.symbol,
                        trade.price,
                        trade.quantity,
                        trade.buyer,
                        trade.seller,
                        trade.timestamp,
                    ]
                )
        return compressed

    def compress_orders(
        self, orders: dict[Symbol, list[Order]]
    ) -> dict[Symbol, list[list[Any]]]:
        compressed = {}
        for symbol, order_list in orders.items():
            compressed[symbol] = [
                [order.price, order.quantity] for order in order_list
            ]
        return compressed

    def compress_observations(self, obs: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in obs.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sugarPrice if hasattr(observation, "sugarPrice") else 0,
                observation.sunlightIndex if hasattr(observation, "sunlightIndex") else 0,
            ]
        return [obs.plainValueObservations, conversion_observations]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def _truncate(self, string: str, max_length: int) -> str:
        if len(string) <= max_length:
            return string
        return string[: max_length - 3] + "..."


logger = Logger()


# ---------------------------------------------------------------------------
# Trader class
# ---------------------------------------------------------------------------

class Trader:
    """
    Main trading algorithm. Dispatches to product-specific strategies
    based on PRODUCT_CONFIG.

    State management:
        - self.state_data: dict loaded from traderData each timestep
        - Contains per-product rolling data (EMA values, price history, etc.)
        - Serialized back to JSON at end of run()
    """

    def __init__(self):
        # Instance variables persist within a single simulation run.
        # Use these for convenience, but always serialize critical state
        # into traderData for safety.
        self.state_data: dict = {}
        # Pairs-arb component orders accumulated during a timestep;
        # merged into result at the end of run().
        self._component_orders: Dict[str, List[Order]] = {}

    def run(
        self, state: TradingState
    ) -> Tuple[Dict[str, List[Order]], int, str]:
        """
        Main entry point called by the simulation each timestep.

        Returns:
            (orders_dict, conversions, traderData_string)
        """
        # --- Deserialize state ---
        self.state_data = self._load_state(state.traderData)
        self._component_orders = {}  # reset each timestep

        result: Dict[str, List[Order]] = {}
        conversions = 0

        # --- Trade each configured product ---
        for product, config in PRODUCT_CONFIG.items():
            if product not in state.order_depths:
                continue

            # Get current position
            position = state.position.get(product, 0)
            pos_limit = config["position_limit"]

            # Dispatch to strategy
            strategy_name = config["strategy"]
            strategy_fn = getattr(self, f"strategy_{strategy_name}", None)

            if strategy_fn is None:
                logger.print(f"WARNING: No strategy '{strategy_name}' for {product}")
                result[product] = []
                continue

            # Call strategy
            orders, conv = strategy_fn(product, state, config, position, pos_limit)

            # Clip orders to position limits
            orders = clip_orders(product, orders, position, pos_limit)

            result[product] = orders
            conversions += conv

            # Log summary
            logger.print(
                f"{product}: pos={position}, orders={len(orders)}, "
                f"conv={conv}"
            )

        # --- Merge component orders from pairs_arb strategies ---
        for comp, comp_orders in self._component_orders.items():
            if comp in result:
                result[comp].extend(comp_orders)
            else:
                result[comp] = comp_orders

        # --- Merge hedge orders from options strategies ---
        hedge_store = self.state_data.pop("_hedge_orders", {})
        for sym, hedge_list in hedge_store.items():
            hedge_orders = [Order(sym, p, q) for p, q in hedge_list]
            if sym in result:
                result[sym].extend(hedge_orders)
            else:
                result[sym] = hedge_orders

        # --- Clean up circular arb cache (not persisted across timesteps) ---
        self.state_data.pop("_circ_cache", None)

        # --- Serialize state ---
        trader_data = self._save_state()

        # --- Flush logs for visualizer ---
        logger.flush(state, result, conversions, trader_data)

        return result, conversions, trader_data

    # -------------------------------------------------------------------
    # State management
    # -------------------------------------------------------------------

    def _load_state(self, trader_data: str) -> dict:
        """Deserialize traderData JSON string to dict."""
        if not trader_data:
            return {}
        try:
            return json.loads(trader_data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_state(self) -> str:
        """Serialize state dict to JSON string."""
        return json.dumps(self.state_data, default=self._json_default)

    def _json_default(self, obj):
        """Handle non-serializable types (deque -> list, etc.)."""
        if isinstance(obj, deque):
            return list(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def _get_product_state(self, product: str) -> dict:
        """Get or initialize per-product state dict."""
        if product not in self.state_data:
            self.state_data[product] = {}
        return self.state_data[product]

    # -------------------------------------------------------------------
    # Strategy: Market make around a fixed fair value
    # -------------------------------------------------------------------

    def strategy_market_make_fixed(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Market making around a known fixed fair value.
        Use for products like Rainforest Resin (P3: fair value = 10,000).

        Config keys:
            fair_value: int — the true/known value
            spread: int — base half-spread in ticks
            skew_factor: float — inventory skew aggressiveness (default 1.0)
        """
        orders: List[Order] = []
        fv = config["fair_value"]
        half_spread = config.get("spread", 2)
        skew_factor = config.get("skew_factor", 1.0)

        # Inventory skew
        norm_pos = position / pos_limit if pos_limit > 0 else 0
        bid_offset = half_spread * (1 + skew_factor * norm_pos)
        ask_offset = half_spread * (1 - skew_factor * norm_pos)
        bid_offset = max(1.0, bid_offset)
        ask_offset = max(1.0, ask_offset)

        bid_price = int(round(fv - bid_offset))
        ask_price = int(round(fv + ask_offset))

        # Also take any mispriced orders in the book
        od = state.order_depths[product]

        # Take cheap asks (below fair value)
        for ask_p in sorted(od.sell_orders.keys()):
            if ask_p < fv:
                ask_vol = abs(od.sell_orders[ask_p])
                orders.append(Order(product, ask_p, ask_vol))

        # Take expensive bids (above fair value)
        for bid_p in sorted(od.buy_orders.keys(), reverse=True):
            if bid_p > fv:
                bid_vol = od.buy_orders[bid_p]
                orders.append(Order(product, bid_p, -bid_vol))

        # Post passive quotes
        buy_qty = pos_limit - position  # max we can buy
        sell_qty = pos_limit + position  # max we can sell

        if buy_qty > 0:
            orders.append(Order(product, bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, ask_price, -sell_qty))

        return orders, 0

    # -------------------------------------------------------------------
    # Strategy: Market make around EMA-estimated fair value
    # -------------------------------------------------------------------

    def strategy_market_make_ema(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Market making using EMA of mid prices as fair value estimate.
        Use for random-walk products like Kelp.

        Config keys:
            ema_alpha: float — EMA smoothing factor
            spread: int — base half-spread
            skew_factor: float — inventory skew (default 1.0)
        """
        orders: List[Order] = []
        od = state.order_depths[product]
        pstate = self._get_product_state(product)

        # Compute current mid
        current_mid = wall_mid(od) or mid_price(od)
        if current_mid is None:
            return orders, 0

        # Update EMA
        alpha = config.get("ema_alpha", 0.3)
        prev_ema = pstate.get("ema")
        fv = ema_update(prev_ema, current_mid, alpha)
        pstate["ema"] = fv

        # Inventory skew
        half_spread = config.get("spread", 2)
        skew_factor = config.get("skew_factor", 1.0)
        norm_pos = position / pos_limit if pos_limit > 0 else 0

        bid_offset = half_spread * (1 + skew_factor * norm_pos)
        ask_offset = half_spread * (1 - skew_factor * norm_pos)
        bid_offset = max(1.0, bid_offset)
        ask_offset = max(1.0, ask_offset)

        bid_price = int(round(fv - bid_offset))
        ask_price = int(round(fv + ask_offset))

        # Take mispriced orders
        for ask_p in sorted(od.sell_orders.keys()):
            if ask_p < fv - 0.5:
                ask_vol = abs(od.sell_orders[ask_p])
                orders.append(Order(product, ask_p, ask_vol))

        for bid_p in sorted(od.buy_orders.keys(), reverse=True):
            if bid_p > fv + 0.5:
                bid_vol = od.buy_orders[bid_p]
                orders.append(Order(product, bid_p, -bid_vol))

        # Post passive quotes
        buy_qty = pos_limit - position
        sell_qty = pos_limit + position

        if buy_qty > 0:
            orders.append(Order(product, bid_price, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, ask_price, -sell_qty))

        return orders, 0

    # -------------------------------------------------------------------
    # Strategy stubs (to be implemented in later sessions)
    # -------------------------------------------------------------------

    def strategy_pairs_arb(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        ETF/basket arbitrage via rolling z-score of the basket-NAV spread.

        When z > z_entry: basket overpriced → sell basket, buy components.
        When z < -z_entry: basket underpriced → buy basket, sell components.
        When |z| < z_exit and position != 0: unwind toward flat.

        Config keys:
            components: dict[symbol, weight]
            z_entry: float — z-score threshold to enter (default 2.0)
            z_exit: float — z-score threshold to exit (default 0.5)
            spread_window: int — rolling window size (default 50)
            max_order_size: int — max units per trade (default 10)
        """
        orders: List[Order] = []
        od = state.order_depths.get(product)
        if od is None:
            return orders, 0

        components = config["components"]
        z_entry = config.get("z_entry", 2.0)
        z_exit = config.get("z_exit", 0.5)
        spread_window = config.get("spread_window", 50)
        max_order_size = config.get("max_order_size", 10)

        basket_mid = mid_price(od)
        if basket_mid is None:
            return orders, 0

        # Compute NAV from component mid prices
        nav = 0.0
        for comp, weight in components.items():
            comp_od = state.order_depths.get(comp)
            if comp_od is None:
                return orders, 0
            comp_mid = mid_price(comp_od)
            if comp_mid is None:
                return orders, 0
            nav += weight * comp_mid

        # Update spread history in persisted state
        spread = basket_mid - nav
        pstate = self._get_product_state(product)
        spread_history = pstate.get("spread_history", [])
        spread_history.append(spread)
        if len(spread_history) > spread_window:
            spread_history = spread_history[-spread_window:]
        pstate["spread_history"] = spread_history

        z = rolling_z_score(spread_history, spread_window)
        logger.print(f"{product} pairs_arb: spread={spread:.2f}, z={z:.2f}")

        basket_bb = best_bid(od)
        basket_ba = best_ask(od)

        if z > z_entry:
            # Basket overpriced: sell basket, buy components
            if basket_bb is not None:
                orders.append(Order(product, basket_bb, -max_order_size))
            for comp, weight in components.items():
                comp_od = state.order_depths.get(comp)
                if comp_od is None:
                    continue
                comp_ba = best_ask(comp_od)
                if comp_ba is None:
                    continue
                comp_qty = int(round(max_order_size * weight))
                comp_pos = state.position.get(comp, 0)
                comp_limit = PRODUCT_CONFIG.get(comp, {}).get("position_limit", 999)
                clipped = clip_orders(
                    comp, [Order(comp, comp_ba, comp_qty)], comp_pos, comp_limit
                )
                self._component_orders.setdefault(comp, []).extend(clipped)

        elif z < -z_entry:
            # Basket underpriced: buy basket, sell components
            if basket_ba is not None:
                orders.append(Order(product, basket_ba, max_order_size))
            for comp, weight in components.items():
                comp_od = state.order_depths.get(comp)
                if comp_od is None:
                    continue
                comp_bb = best_bid(comp_od)
                if comp_bb is None:
                    continue
                comp_qty = int(round(max_order_size * weight))
                comp_pos = state.position.get(comp, 0)
                comp_limit = PRODUCT_CONFIG.get(comp, {}).get("position_limit", 999)
                clipped = clip_orders(
                    comp, [Order(comp, comp_bb, -comp_qty)], comp_pos, comp_limit
                )
                self._component_orders.setdefault(comp, []).extend(clipped)

        elif abs(z) < z_exit and position != 0:
            # Unwind basket position toward flat
            if position > 0 and basket_bb is not None:
                orders.append(Order(product, basket_bb, -min(position, max_order_size)))
            elif position < 0 and basket_ba is not None:
                orders.append(Order(product, basket_ba, min(-position, max_order_size)))

        return orders, 0

    def strategy_informed_trader(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Track net flow of informed traders; trade directionally on signal.

        Config keys:
            tracked_traders: list[str] — trader IDs to monitor
            flow_window: int — timesteps to aggregate flow over (default 10)
            signal_threshold: float — net flow to trigger direction (default 5)
            base_spread: int — half-spread for passive quoting (default 2)
            ema_alpha: float — EMA smoothing for fair value (default 0.3)
        """
        orders: List[Order] = []
        od = state.order_depths.get(product)
        if od is None:
            return orders, 0

        tracked_traders = config.get("tracked_traders", [])
        flow_window = config.get("flow_window", 10)
        signal_threshold = config.get("signal_threshold", 5)
        base_spread = config.get("base_spread", 2)
        alpha = config.get("ema_alpha", 0.3)

        pstate = self._get_product_state(product)

        # Update EMA fair value
        current_mid = wall_mid(od) or mid_price(od)
        if current_mid is None:
            return orders, 0
        fv = ema_update(pstate.get("ema"), current_mid, alpha)
        pstate["ema"] = fv
        fv_int = int(round(fv))

        # Update per-trader flow history from this timestep's market trades
        product_trades = state.market_trades.get(product, [])
        flow_history = pstate.get("flow_history", {})
        for trader_id in tracked_traders:
            net = net_trade_flow(product_trades, trader_id)
            history = flow_history.setdefault(trader_id, [])
            history.append(net)
            if len(history) > flow_window:
                flow_history[trader_id] = history[-flow_window:]
        pstate["flow_history"] = flow_history

        # Aggregate net flow across all tracked traders over the window
        aggregate_flow = sum(
            sum(flow_history.get(t, [])) for t in tracked_traders
        )
        logger.print(
            f"{product} informed_trader: fv={fv:.2f}, agg_flow={aggregate_flow}"
        )

        buy_qty = pos_limit - position
        sell_qty = pos_limit + position

        if aggregate_flow > signal_threshold:
            # Informed trader is buying → aggressively take asks
            for ask_p in sorted(od.sell_orders.keys()):
                if ask_p <= fv_int + base_spread:
                    orders.append(Order(product, ask_p, abs(od.sell_orders[ask_p])))
        elif aggregate_flow < -signal_threshold:
            # Informed trader is selling → aggressively take bids
            for bid_p in sorted(od.buy_orders.keys(), reverse=True):
                if bid_p >= fv_int - base_spread:
                    orders.append(Order(product, bid_p, -od.buy_orders[bid_p]))
        else:
            # No signal: passive market making around fair value
            if buy_qty > 0:
                orders.append(Order(product, fv_int - base_spread, buy_qty))
            if sell_qty > 0:
                orders.append(Order(product, fv_int + base_spread, -sell_qty))

        return orders, 0

    def strategy_circular_arb(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Circular/triangular arbitrage across products acting as exchange rates.

        Detects profitable cycles by checking if the product of mid rates
        around the cycle exceeds 1.0 (profit > min_profit_bps). Each leg of
        the cycle gets its own call; this method only places orders for its
        own product.

        The cycle profit computation is cached in self.state_data["_circ_cache"]
        keyed by timestamp to avoid recomputation across legs.

        Config keys:
            cycle: list[str] — product symbols forming the cycle
            rate_type: "mid" or "best"
            min_profit_bps: float — minimum profit in basis points (default 10)
            max_order_size: int — max units per leg (default 20)
            cycle_role: "buy" or "sell" — direction for this leg
        """
        orders: List[Order] = []
        cycle = config["cycle"]
        rate_type = config.get("rate_type", "mid")
        min_profit_bps = config.get("min_profit_bps", 10)
        max_order_size = config.get("max_order_size", 20)
        cycle_role = config.get("cycle_role", "buy")

        # --- Cache cycle computation per timestamp ---
        cache_key = "_circ_cache"
        if cache_key not in self.state_data:
            self.state_data[cache_key] = {}
        cache = self.state_data[cache_key]
        ts_key = str(state.timestamp)

        cycle_tuple_key = ",".join(cycle)
        cache_entry_key = f"{ts_key}:{cycle_tuple_key}"

        if cache_entry_key not in cache:
            # Compute rates for each leg
            rates = []
            for leg in cycle:
                leg_od = state.order_depths.get(leg)
                if leg_od is None:
                    rates = None
                    break
                if rate_type == "best":
                    bb = best_bid(leg_od)
                    ba = best_ask(leg_od)
                    if bb is None or ba is None:
                        rates = None
                        break
                    rates.append((bb, ba, mid_price(leg_od)))
                else:
                    m = mid_price(leg_od)
                    if m is None:
                        rates = None
                        break
                    rates.append((None, None, m))

            if rates is None:
                cache[cache_entry_key] = {"profitable": False}
            else:
                # Product of mid rates around the cycle
                product_of_mids = 1.0
                for _, _, m in rates:
                    product_of_mids *= m
                # For exchange rates, profit = (product_of_rates - 1) * 10000 bps
                # But if products are prices not rates, we check the
                # round-trip: does buying through the cycle yield > 1?
                # Use log-sum for numerical stability
                log_sum = sum(math.log(m) for _, _, m in rates if m > 0)
                profit_bps = (math.exp(log_sum) - 1.0) * 10000.0
                cache[cache_entry_key] = {
                    "profitable": abs(profit_bps) >= min_profit_bps,
                    "profit_bps": profit_bps,
                    "rates": rates,
                }
        else:
            pass  # already computed

        result = cache.get(cache_entry_key, {"profitable": False})

        if not result.get("profitable", False):
            return orders, 0

        profit_bps = result.get("profit_bps", 0)
        od = state.order_depths.get(product)
        if od is None:
            return orders, 0

        # Determine order direction based on cycle_role and profit direction
        if profit_bps > 0 and cycle_role == "buy":
            ba = best_ask(od)
            if ba is not None:
                orders.append(Order(product, ba, max_order_size))
        elif profit_bps > 0 and cycle_role == "sell":
            bb = best_bid(od)
            if bb is not None:
                orders.append(Order(product, bb, -max_order_size))
        elif profit_bps < 0 and cycle_role == "buy":
            bb = best_bid(od)
            if bb is not None:
                orders.append(Order(product, bb, -max_order_size))
        elif profit_bps < 0 and cycle_role == "sell":
            ba = best_ask(od)
            if ba is not None:
                orders.append(Order(product, ba, max_order_size))

        logger.print(
            f"{product} circular_arb: profit_bps={profit_bps:.1f}, "
            f"role={cycle_role}, orders={len(orders)}"
        )
        return orders, 0

    def strategy_options(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Options pricing via Black-Scholes with IV mean-reversion trading.

        Computes implied vol from the option mid price, tracks IV history,
        and trades when IV z-score crosses entry/exit thresholds.
        Optionally generates delta hedge orders for the underlying, stored
        in self.state_data["_hedge_orders"] for run() to merge.

        Config keys:
            underlying: str — symbol of underlying (e.g. "VOLCANIC_ROCK")
            strike: int
            expiry_days: int — days to expiry (T = expiry_days / 252)
            risk_free_rate: float (default 0.0)
            iv_window: int — rolling window for IV history (default 20)
            iv_z_entry: float — z-score to enter IV trade (default 1.5)
            iv_z_exit: float — z-score to exit (default 0.5)
            delta_hedge: bool — whether to hedge with underlying (default False)
        """
        orders: List[Order] = []
        underlying_sym = config["underlying"]
        strike = config["strike"]
        T = config.get("expiry_days", 5) / 252.0
        r = config.get("risk_free_rate", 0.0)
        iv_window = config.get("iv_window", 20)
        iv_z_entry = config.get("iv_z_entry", 1.5)
        iv_z_exit = config.get("iv_z_exit", 0.5)
        do_hedge = config.get("delta_hedge", False)
        max_order_size = config.get("max_order_size", 20)

        # Get underlying spot price
        underlying_od = state.order_depths.get(underlying_sym)
        if underlying_od is None:
            return orders, 0
        spot = mid_price(underlying_od)
        if spot is None:
            return orders, 0

        # Get option mid price
        od = state.order_depths.get(product)
        if od is None:
            return orders, 0
        opt_mid = mid_price(od)
        if opt_mid is None:
            return orders, 0

        # Compute implied vol
        iv = implied_vol(opt_mid, spot, strike, T, r, "call")
        if iv is None:
            return orders, 0

        # Track IV history
        pstate = self._get_product_state(product)
        iv_history = pstate.get("iv_history", [])
        iv_history.append(iv)
        if len(iv_history) > iv_window:
            iv_history = iv_history[-iv_window:]
        pstate["iv_history"] = iv_history

        z = rolling_z_score(iv_history, iv_window)
        logger.print(f"{product} options: iv={iv:.4f}, z={z:.2f}, spot={spot:.1f}")

        opt_bb = best_bid(od)
        opt_ba = best_ask(od)

        if z > iv_z_entry:
            # IV is high → sell options (expect IV to fall, options overpriced)
            if opt_bb is not None:
                orders.append(Order(product, opt_bb, -max_order_size))
        elif z < -iv_z_entry:
            # IV is low → buy options (expect IV to rise, options underpriced)
            if opt_ba is not None:
                orders.append(Order(product, opt_ba, max_order_size))
        elif abs(z) < iv_z_exit and position != 0:
            # Unwind toward flat
            if position > 0 and opt_bb is not None:
                orders.append(Order(product, opt_bb, -min(position, max_order_size)))
            elif position < 0 and opt_ba is not None:
                orders.append(Order(product, opt_ba, min(-position, max_order_size)))

        # Delta hedging: store hedge orders for run() to merge
        if do_hedge and orders:
            delta = bs_delta(spot, strike, T, r, iv)
            # Net option delta from position + new orders
            new_opt_qty = sum(o.quantity for o in orders)
            total_opt_pos = position + new_opt_qty
            # Hedge: short delta * option_position shares of underlying
            hedge_qty = -int(round(delta * total_opt_pos))
            if hedge_qty != 0:
                underlying_bb = best_bid(underlying_od)
                underlying_ba = best_ask(underlying_od)
                if hedge_qty > 0 and underlying_ba is not None:
                    hedge_order = Order(underlying_sym, underlying_ba, hedge_qty)
                elif hedge_qty < 0 and underlying_bb is not None:
                    hedge_order = Order(underlying_sym, underlying_bb, hedge_qty)
                else:
                    hedge_order = None
                if hedge_order is not None:
                    # Clip to underlying position limit
                    u_pos = state.position.get(underlying_sym, 0)
                    u_limit = PRODUCT_CONFIG.get(underlying_sym, {}).get(
                        "position_limit", 400
                    )
                    clipped = clip_orders(
                        underlying_sym, [hedge_order], u_pos, u_limit
                    )
                    if clipped:
                        hedge_store = self.state_data.setdefault("_hedge_orders", {})
                        hedge_store.setdefault(underlying_sym, []).extend(
                            [(o.price, o.quantity) for o in clipped]
                        )

        return orders, 0

    def strategy_cross_exchange(
        self,
        product: str,
        state: TradingState,
        config: dict,
        position: int,
        pos_limit: int,
    ) -> Tuple[List[Order], int]:
        """
        Cross-exchange arbitrage using the conversion mechanism.

        implied_bid = obs.bidPrice - obs.exportTariff - obs.transportFees - storage_cost
        implied_ask = obs.askPrice + obs.importTariff + obs.transportFees

        If local_ask < implied_bid - spread_buffer: buy local, convert to sell foreign.
        If local_bid > implied_ask + spread_buffer: sell local, convert to buy foreign.
        Also post passive quotes around implied mid.

        Config keys:
            conversion_product: str — key in conversionObservations
            storage_cost: float — per-unit holding cost (default 0.0)
            spread_buffer: float — minimum profit margin (default 1.0)
            max_conversion: int — max units to convert per timestep (default 10)
        """
        orders: List[Order] = []
        conversion_product = config.get("conversion_product", product)
        storage_cost = config.get("storage_cost", 0.0)
        spread_buffer = config.get("spread_buffer", 1.0)
        max_conversion = config.get("max_conversion", 10)

        obs = state.observations.conversionObservations.get(conversion_product)
        if obs is None:
            return orders, 0

        implied_bid = obs.bidPrice - obs.exportTariff - obs.transportFees - storage_cost
        implied_ask = obs.askPrice + obs.importTariff + obs.transportFees
        implied_mid = (implied_bid + implied_ask) / 2.0

        od = state.order_depths.get(product)
        if od is None:
            return orders, 0

        local_ba = best_ask(od)
        local_bb = best_bid(od)
        conversions = 0

        if local_ba is not None and local_ba < implied_bid - spread_buffer:
            # Buy locally cheap, convert to sell on foreign exchange
            buy_qty = min(
                abs(od.sell_orders[local_ba]),
                max_conversion,
                pos_limit - position,
            )
            if buy_qty > 0:
                orders.append(Order(product, local_ba, buy_qty))
                conversions = buy_qty

        elif local_bb is not None and local_bb > implied_ask + spread_buffer:
            # Sell locally expensive, convert to buy from foreign exchange
            sell_qty = min(
                od.buy_orders[local_bb],
                max_conversion,
                pos_limit + position,
            )
            if sell_qty > 0:
                orders.append(Order(product, local_bb, -sell_qty))
                conversions = -sell_qty

        # Post passive quotes around implied mid to capture additional spread
        implied_mid_int = int(round(implied_mid))
        half_spread = max(1, int(round(spread_buffer)))
        buy_qty = pos_limit - position
        sell_qty = pos_limit + position
        if buy_qty > 0:
            orders.append(Order(product, implied_mid_int - half_spread, buy_qty))
        if sell_qty > 0:
            orders.append(Order(product, implied_mid_int + half_spread, -sell_qty))

        logger.print(
            f"{product} cross_exchange: impl_bid={implied_bid:.2f}, "
            f"impl_ask={implied_ask:.2f}, conv={conversions}"
        )
        return orders, conversions
