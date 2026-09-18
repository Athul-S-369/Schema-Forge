"""
Focused synthetic data engine.

Scope (v1):
  1. Schema understanding — introspect SQLAlchemy metadata into a relationship graph
  2. Constraint awareness — never emit rows that violate CHECK / UNIQUE / NOT NULL
  3. Referential integrity — generate tables in dependency order so FKs stay valid
  4. Realistic distributions — Zipf, normal, skewed (not flat uniform noise)
  5. Deterministic seeds — same seed ⇒ same dataset

Out of scope for this version:
  streaming/chunked scale, validation reports, multi-format exporters,
  anonymization, benchmark profiles, edge-case packs, API mocks,
  event streams, plugin systems.
"""

from .generator import SynthEngine
from .rng import SeedContext
from .schema import SchemaGraph, build_schema_graph

__all__ = [
    "SchemaGraph",
    "SeedContext",
    "SynthEngine",
    "build_schema_graph",
]
