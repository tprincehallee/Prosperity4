"""
Order book utility functions.

Functions for extracting information from OrderDepth objects:
prices, spreads, fair value estimates, and depth analysis.
"""

from typing import List, Optional, Tuple, Dict

# We import from datamodel for type hints. During submission, these
# will come from the competition's datamodel module.
from datamodel import OrderDepth, Order, Trade


def best_bid(order_depth: OrderDepth) -> Optional[int]:
    """Return the highest bid price, or None if no bids."""
    if not order_depth.buy_orders:
        return None
    return max(order_depth.buy_orders.keys())


def best_ask(order_depth: OrderDepth) -> Optional[int]:
    """Return the lowest ask price, or None if no asks."""
    if not order_depth.sell_orders:
        return None
    return min(order_depth.sell_orders.keys())


def best_bid_volume(order_depth: OrderDepth) -> int:
    """Return the volume at the best bid, or 0 if no bids."""
    bb = best_bid(order_depth)
    if bb is None:
        return 0
    return order_depth.buy_orders[bb]


def best_ask_volume(order_depth: OrderDepth) -> int:
    """Return the volume at the best ask (negative in OrderDepth), or 0."""
    ba = best_ask(order_depth)
    if ba is None:
        return 0
    return order_depth.sell_orders[ba]  # Note: this is negative


def mid_price(order_depth: OrderDepth) -> Optional[float]:
    """
    Simple midpoint of best bid and best ask.

    Returns None if either side of the book is empty.
    """
    bb = best_bid(order_depth)
    ba = best_ask(order_depth)
    if bb is None or ba is None:
        return None
    return (bb + ba) / 2.0


def spread(order_depth: OrderDepth) -> Optional[int]:
    """
    Bid-ask spread in ticks.

    Returns None if either side is empty.
    """
    bb = best_bid(order_depth)
    ba = best_ask(order_depth)
    if bb is None or ba is None:
        return None
    return ba - bb


def wall_mid(order_depth: OrderDepth) -> Optional[float]:
    """
    Volume-weighted midpoint ("Wall Mid").

    Weights the midpoint by the volume on each side of the book at the
    top of book. When one side has much more volume, the fair value
    estimate shifts toward the other side (since the "wall" acts as
    support/resistance).

    Formula: (best_bid * |ask_vol| + best_ask * bid_vol) / (bid_vol + |ask_vol|)

    Returns None if either side is empty.
    """
    bb = best_bid(order_depth)
    ba = best_ask(order_depth)
    if bb is None or ba is None:
        return None

    bid_vol = order_depth.buy_orders[bb]           # positive
    ask_vol = abs(order_depth.sell_orders[ba])      # make positive

    total_vol = bid_vol + ask_vol
    if total_vol == 0:
        return (bb + ba) / 2.0

    return (bb * ask_vol + ba * bid_vol) / total_vol


def weighted_mid(order_depth: OrderDepth, levels: int = 3) -> Optional[float]:
    """
    Multi-level volume-weighted midpoint using top N levels of the book.

    Args:
        order_depth: Current order book.
        levels: Number of price levels to consider on each side.

    Returns:
        Weighted mid price, or None if book is empty.
    """
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None

    # Sort bids descending, asks ascending
    sorted_bids = sorted(order_depth.buy_orders.items(), key=lambda x: -x[0])[:levels]
    sorted_asks = sorted(order_depth.sell_orders.items(), key=lambda x: x[0])[:levels]

    bid_vwap = sum(p * v for p, v in sorted_bids) / sum(v for _, v in sorted_bids)
    ask_vwap = sum(p * abs(v) for p, v in sorted_asks) / sum(abs(v) for _, v in sorted_asks)

    total_bid_vol = sum(v for _, v in sorted_bids)
    total_ask_vol = sum(abs(v) for _, v in sorted_asks)
    total = total_bid_vol + total_ask_vol

    if total == 0:
        return (bid_vwap + ask_vwap) / 2.0

    return (bid_vwap * total_ask_vol + ask_vwap * total_bid_vol) / total


def book_imbalance(order_depth: OrderDepth) -> float:
    """
    Compute order book imbalance at best bid/ask.

    Returns a value in [-1, 1]:
        +1 = all volume on bid side (bullish pressure)
        -1 = all volume on ask side (bearish pressure)
         0 = balanced

    Returns 0.0 if book is empty.
    """
    bb = best_bid(order_depth)
    ba = best_ask(order_depth)
    if bb is None or ba is None:
        return 0.0

    bid_vol = order_depth.buy_orders[bb]
    ask_vol = abs(order_depth.sell_orders[ba])
    total = bid_vol + ask_vol

    if total == 0:
        return 0.0

    return (bid_vol - ask_vol) / total


def total_bid_volume(order_depth: OrderDepth) -> int:
    """Sum of all bid volumes across all price levels."""
    return sum(order_depth.buy_orders.values())


def total_ask_volume(order_depth: OrderDepth) -> int:
    """Sum of all ask volumes (returns positive value)."""
    return sum(abs(v) for v in order_depth.sell_orders.values())


def sorted_bids(order_depth: OrderDepth) -> List[Tuple[int, int]]:
    """Return bids sorted by price descending: [(price, volume), ...]."""
    return sorted(order_depth.buy_orders.items(), key=lambda x: -x[0])


def sorted_asks(order_depth: OrderDepth) -> List[Tuple[int, int]]:
    """Return asks sorted by price ascending: [(price, abs_volume), ...]."""
    return sorted(
        ((p, abs(v)) for p, v in order_depth.sell_orders.items()),
        key=lambda x: x[0],
    )


def trades_vwap(trades: List[Trade]) -> Optional[float]:
    """
    Compute VWAP from a list of Trade objects.

    Returns None if no trades.
    """
    if not trades:
        return None
    total_value = sum(t.price * t.quantity for t in trades)
    total_volume = sum(t.quantity for t in trades)
    if total_volume == 0:
        return None
    return total_value / total_volume


def net_trade_flow(trades: List[Trade], trader_id: str) -> int:
    """
    Compute net buying (+) or selling (-) volume by a specific trader.

    Args:
        trades: List of Trade objects.
        trader_id: The trader ID to track (e.g., "Olivia").

    Returns:
        Positive = net buyer, negative = net seller.
    """
    net = 0
    for t in trades:
        if t.buyer == trader_id:
            net += t.quantity
        if t.seller == trader_id:
            net -= t.quantity
    return net


def make_buy_order(symbol: str, price: int, quantity: int) -> Order:
    """Create a buy order (quantity will be made positive)."""
    return Order(symbol, price, abs(quantity))


def make_sell_order(symbol: str, price: int, quantity: int) -> Order:
    """Create a sell order (quantity will be made negative)."""
    return Order(symbol, price, -abs(quantity))
