"""
Black-Scholes option pricing utilities.

All functions use only the math standard library — no scipy/numpy required.
These are also inlined in trader.py for submission.
"""

import math
from typing import Optional


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
) -> Optional[float]:
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
