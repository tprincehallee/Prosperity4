"""
Mathematical utility functions for trading strategies.

All functions are designed to be stateless and composable.
State (rolling windows, EMA values) is maintained in traderData
and passed in as arguments.
"""

from collections import deque
from typing import List, Optional, Tuple
import math


def ema_update(current_ema: Optional[float], new_value: float, alpha: float) -> float:
    """
    Update an exponential moving average with a new observation.

    Args:
        current_ema: Previous EMA value, or None if this is the first observation.
        new_value: New data point.
        alpha: Smoothing factor in (0, 1). Higher = more weight on recent data.
               Common values: 0.2 (slow), 0.3 (medium), 0.5 (fast).

    Returns:
        Updated EMA value.
    """
    if current_ema is None:
        return new_value
    return alpha * new_value + (1 - alpha) * current_ema


def ema_from_span(span: int) -> float:
    """
    Convert a span (number of periods) to an EMA alpha.

    The standard formula: alpha = 2 / (span + 1).
    Example: span=10 -> alpha=0.1818, span=20 -> alpha=0.0952.
    """
    return 2.0 / (span + 1)


def z_score(values: List[float], current_value: Optional[float] = None) -> float:
    """
    Compute z-score of the last value in a series (or a given value) relative
    to the series' mean and standard deviation.

    Args:
        values: Historical observations (at least 2 required).
        current_value: If provided, compute z-score of this value against
                       the series. Otherwise uses the last element.

    Returns:
        Z-score (number of standard deviations from mean).
        Returns 0.0 if insufficient data or zero variance.
    """
    if len(values) < 2:
        return 0.0

    val = current_value if current_value is not None else values[-1]
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)

    if variance == 0:
        return 0.0

    std = math.sqrt(variance)
    return (val - mean) / std


def rolling_z_score(
    values: List[float], window: int, current_value: Optional[float] = None
) -> float:
    """
    Compute z-score using only the last `window` observations.

    Args:
        values: Full historical series.
        window: Number of recent observations to use.
        current_value: Optional override for the test value.

    Returns:
        Z-score computed over the rolling window.
    """
    if len(values) < 2:
        return 0.0
    windowed = values[-window:] if len(values) >= window else values
    return z_score(windowed, current_value)


def vwap(prices: List[float], volumes: List[float]) -> float:
    """
    Compute volume-weighted average price.

    Args:
        prices: List of trade prices.
        volumes: List of trade volumes (must be same length as prices).

    Returns:
        VWAP, or 0.0 if no volume.
    """
    if not prices or not volumes or len(prices) != len(volumes):
        return 0.0

    total_volume = sum(abs(v) for v in volumes)
    if total_volume == 0:
        return 0.0

    return sum(p * abs(v) for p, v in zip(prices, volumes)) / total_volume


def linear_regression(values: List[float]) -> Tuple[float, float]:
    """
    Simple linear regression on a series (x = 0, 1, 2, ..., n-1).

    Args:
        values: Y-values in order.

    Returns:
        (slope, intercept) tuple. slope > 0 means uptrend.
        Returns (0.0, values[-1]) if fewer than 2 points.
    """
    n = len(values)
    if n < 2:
        return (0.0, values[-1] if values else 0.0)

    # x = 0, 1, ..., n-1
    sum_x = n * (n - 1) / 2
    sum_y = sum(values)
    sum_xy = sum(i * v for i, v in enumerate(values))
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return (0.0, values[-1])

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    return (slope, intercept)


def linear_regression_predict(values: List[float], steps_ahead: int = 1) -> float:
    """
    Predict a future value using linear regression extrapolation.

    Args:
        values: Historical series.
        steps_ahead: How many steps into the future to predict.

    Returns:
        Predicted value.
    """
    slope, intercept = linear_regression(values)
    return intercept + slope * (len(values) - 1 + steps_ahead)


def rolling_mean(values: List[float], window: Optional[int] = None) -> float:
    """
    Compute mean of the last `window` values (or all values if window is None).
    """
    if not values:
        return 0.0
    if window is not None and len(values) > window:
        values = values[-window:]
    return sum(values) / len(values)


def rolling_std(values: List[float], window: Optional[int] = None) -> float:
    """
    Compute standard deviation of the last `window` values.
    """
    if len(values) < 2:
        return 0.0
    if window is not None and len(values) > window:
        values = values[-window:]
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def bollinger_bands(
    values: List[float], window: int = 20, num_std: float = 2.0
) -> Tuple[float, float, float]:
    """
    Compute Bollinger Bands.

    Args:
        values: Price series.
        window: Lookback period for mean and std.
        num_std: Number of standard deviations for bands.

    Returns:
        (upper_band, middle_band, lower_band).
    """
    mid = rolling_mean(values, window)
    std = rolling_std(values, window)
    return (mid + num_std * std, mid, mid - num_std * std)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))
