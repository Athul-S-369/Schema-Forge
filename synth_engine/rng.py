"""Deterministic seeding — same seed ⇒ same dataset."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from faker import Faker


def _stable_mix(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**31 - 1)


@dataclass
class SeedContext:
    """Single source of randomness for reproducible generation."""

    seed: int = 42
    _rng: random.Random = field(init=False, repr=False)
    _faker: Faker = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.reset(self.seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self._rng = random.Random(self.seed)
        self._faker = Faker()
        self._faker.seed_instance(self.seed)

    @property
    def rng(self) -> random.Random:
        return self._rng

    @property
    def faker(self) -> Faker:
        return self._faker

    def derive(self, label: str) -> "SeedContext":
        """Stable child stream keyed by label (table name) — order-independent."""
        return SeedContext(seed=_stable_mix(self.seed, label))
