"""Realistic distributions — Zipf, normal, skewed; not flat uniform noise."""

from __future__ import annotations

import math
from typing import Sequence, TypeVar

from .rng import SeedContext

T = TypeVar("T")


def zipf_weights(n: int, alpha: float = 1.2) -> list[float]:
    """Power-law weights: rank 1 is most common (classic long-tail)."""
    if n <= 0:
        return []
    weights = [1.0 / (rank**alpha) for rank in range(1, n + 1)]
    total = sum(weights)
    return [w / total for w in weights]


def zipf_choice(ctx: SeedContext, population: Sequence[T], alpha: float = 1.2) -> T:
    if not population:
        raise ValueError("zipf_choice on empty population")
    weights = zipf_weights(len(population), alpha)
    return ctx.rng.choices(list(population), weights=weights, k=1)[0]


def skewed_choice(
    ctx: SeedContext,
    population: Sequence[T],
    *,
    hot_fraction: float = 0.2,
    hot_mass: float = 0.8,
) -> T:
    """
    Prefer a head subset of the population (e.g. popular products/sellers).
    First hot_fraction of items receive hot_mass of probability mass.
    """
    items = list(population)
    n = len(items)
    if n == 0:
        raise ValueError("skewed_choice on empty population")
    if n == 1:
        return items[0]

    hot_n = max(1, int(math.ceil(n * hot_fraction)))
    cold_n = n - hot_n
    hot_w = hot_mass / hot_n
    cold_w = ((1.0 - hot_mass) / cold_n) if cold_n else 0.0
    weights = [hot_w] * hot_n + [cold_w] * cold_n
    return ctx.rng.choices(items, weights=weights, k=1)[0]


def normal_int(
    ctx: SeedContext,
    *,
    mean: float,
    std: float,
    low: int | None = None,
    high: int | None = None,
) -> int:
    value = int(round(ctx.rng.gauss(mean, std)))
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def normal_float(
    ctx: SeedContext,
    *,
    mean: float,
    std: float,
    low: float | None = None,
    high: float | None = None,
) -> float:
    value = ctx.rng.gauss(mean, std)
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def lognormal_positive(
    ctx: SeedContext,
    *,
    mean: float = 0.0,
    sigma: float = 0.75,
    low: float = 0.01,
    high: float | None = None,
) -> float:
    """Right-skewed positive values (prices, weights, amounts)."""
    value = ctx.rng.lognormvariate(mean, sigma)
    value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def weighted_enum(ctx: SeedContext, options: Sequence[T], weights: Sequence[float]) -> T:
    return ctx.rng.choices(list(options), weights=list(weights), k=1)[0]
