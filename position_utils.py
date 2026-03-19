"""
Position management utilities.

Core infrastructure for ensuring orders respect position limits.
Every strategy module should route orders through these functions
before returning them. A single position-limit violation silently
rejects the entire order — so this is safety-critical code.
"""

from typing import List, Tuple
from datamodel import Order


def get_position(positions: dict, symbol: str) -> int:
    """
    Safely get current position for a symbol.

    Returns 0 if the symbol has no position entry (common on first timestep).
    """
    return positions.get(symbol, 0)


def clip_orders(
    symbol: str,
    orders: List[Order],
    current_position: int,
    position_limit: int,
) -> List[Order]:
    """
    Clip a list of orders so the resulting position never exceeds limits.

    Processes orders sequentially, simulating their effect on position.
    Each order's quantity is reduced (or removed entirely) if it would
    breach the limit. Buy orders are clipped against +limit, sell orders
    against -limit.

    Args:
        symbol: Product symbol.
        orders: Proposed orders (mixed buys and sells).
        current_position: Current position before these orders execute.
        position_limit: Absolute position limit (symmetric: -limit to +limit).

    Returns:
        New list of clipped orders. Orders with zero quantity are removed.
    """
    clipped = []
    simulated_pos = current_position

    for order in orders:
        qty = order.quantity
        if qty > 0:
            # Buy: position increases
            max_buy = position_limit - simulated_pos
            if max_buy <= 0:
                continue  # Already at or beyond limit
            clipped_qty = min(qty, max_buy)
        elif qty < 0:
            # Sell: position decreases
            max_sell = position_limit + simulated_pos  # max absolute sell qty
            if max_sell <= 0:
                continue  # Already at or beyond negative limit
            clipped_qty = -min(abs(qty), max_sell)
        else:
            continue  # Zero quantity, skip

        clipped.append(Order(symbol, order.price, clipped_qty))
        simulated_pos += clipped_qty

    return clipped


def max_buy_quantity(current_position: int, position_limit: int) -> int:
    """
    Maximum quantity you can buy without exceeding the position limit.

    Returns 0 if already at or beyond the limit.
    """
    return max(0, position_limit - current_position)


def max_sell_quantity(current_position: int, position_limit: int) -> int:
    """
    Maximum quantity you can sell (as a positive number) without exceeding
    the negative position limit.

    Returns 0 if already at or beyond the negative limit.
    """
    return max(0, position_limit + current_position)


def inventory_skew(
    current_position: int,
    position_limit: int,
    base_spread: float,
    skew_factor: float = 1.0,
) -> Tuple[float, float]:
    """
    Compute inventory-aware bid/ask spread adjustment.

    When holding a large positive position, widen the bid spread (less
    eager to buy more) and tighten the ask spread (more eager to sell).
    Vice versa for negative positions.

    Args:
        current_position: Current position.
        position_limit: Absolute position limit.
        base_spread: Base half-spread (distance from fair value to quote).
        skew_factor: How aggressively to skew. 1.0 = linear.
                     Higher values = more aggressive inventory reduction.

    Returns:
        (bid_offset, ask_offset): Adjustments to subtract from fair value
        for bid, and add to fair value for ask. Both are positive.

        Example: fair_value=100, bid_offset=3, ask_offset=1
            -> bid at 97, ask at 101 (eager to sell)
    """
    if position_limit == 0:
        return (base_spread, base_spread)

    # Normalized position: -1.0 (max short) to +1.0 (max long)
    norm_pos = current_position / position_limit

    # Skew: when long, increase bid offset (less eager to buy)
    #        and decrease ask offset (more eager to sell)
    bid_offset = base_spread * (1 + skew_factor * norm_pos)
    ask_offset = base_spread * (1 - skew_factor * norm_pos)

    # Ensure offsets are non-negative (at extreme positions, one side
    # might go negative — clamp to a minimum of 0)
    bid_offset = max(0.0, bid_offset)
    ask_offset = max(0.0, ask_offset)

    return (bid_offset, ask_offset)


def should_reduce_position(
    current_position: int,
    position_limit: int,
    threshold: float = 0.8,
) -> int:
    """
    Check if position is large enough that we should actively reduce it.

    Args:
        current_position: Current position.
        position_limit: Absolute limit.
        threshold: Fraction of limit at which to trigger reduction (0-1).

    Returns:
        +1 if should sell to reduce (position too long).
        -1 if should buy to reduce (position too short).
         0 if position is within threshold.
    """
    if position_limit == 0:
        return 0
    ratio = current_position / position_limit
    if ratio > threshold:
        return 1
    elif ratio < -threshold:
        return -1
    return 0


def split_orders_by_side(orders: List[Order]) -> Tuple[List[Order], List[Order]]:
    """
    Split a list of orders into buy orders and sell orders.

    Returns:
        (buy_orders, sell_orders) — each sorted by price (buys descending,
        sells ascending).
    """
    buys = sorted(
        [o for o in orders if o.quantity > 0],
        key=lambda o: -o.price,
    )
    sells = sorted(
        [o for o in orders if o.quantity < 0],
        key=lambda o: o.price,
    )
    return buys, sells
