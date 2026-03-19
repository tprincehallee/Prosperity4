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
        self, product, state, config, position, pos_limit
    ) -> Tuple[List[Order], int]:
        """ETF/basket arbitrage. Trades spread between basket and components."""
        # TODO: Session 3
        return [], 0

    def strategy_informed_trader(
        self, product, state, config, position, pos_limit
    ) -> Tuple[List[Order], int]:
        """Detect and follow informed trader (Olivia) signals."""
        # TODO: Session 3
        return [], 0

    def strategy_circular_arb(
        self, product, state, config, position, pos_limit
    ) -> Tuple[List[Order], int]:
        """Circular/triangular arbitrage across exchange rates."""
        # TODO: Session 3
        return [], 0

    def strategy_options(
        self, product, state, config, position, pos_limit
    ) -> Tuple[List[Order], int]:
        """Options pricing and delta hedging."""
        # TODO: Session 3
        return [], 0

    def strategy_cross_exchange(
        self, product, state, config, position, pos_limit
    ) -> Tuple[List[Order], int]:
        """Cross-exchange arbitrage using conversions."""
        # TODO: Session 3
        return [], 0
