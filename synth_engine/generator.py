"""
Orchestrator: schema graph → dependency order → constraint-safe rows.

Referential integrity: every FK value is sampled from already-generated parent keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from .constraints import ConstraintTracker
from .distributions import skewed_choice, zipf_choice
from .rng import SeedContext
from .schema import SchemaGraph, TableNode, build_schema_graph
from .values import apply_derived_checks, generate_scalar


@dataclass
class GeneratedStore:
    """In-memory parent keys for FK resolution (and optional ORM objects)."""

    keys: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add(self, table: str, row: dict[str, Any], pk_cols: tuple[str, ...]) -> None:
        self.rows.setdefault(table, []).append(row)
        pk = {c: row[c] for c in pk_cols if c in row}
        if pk:
            self.keys.setdefault(table, []).append(pk)

    def parent_keys(self, table: str) -> list[dict[str, Any]]:
        return self.keys.get(table, [])


RowHook = Callable[[str, dict[str, Any], SeedContext], dict[str, Any] | None]


@dataclass
class SynthEngine:
    graph: SchemaGraph
    seed: int = 42
    default_rows: int = 20
    table_counts: dict[str, int] = field(default_factory=dict)
    fk_distribution: str = "zipf"  # zipf | skewed | uniform
    row_hook: RowHook | None = None

    @classmethod
    def from_metadata(cls, source, **kwargs) -> "SynthEngine":
        return cls(graph=build_schema_graph(source), **kwargs)

    def count_for(self, table: str) -> int:
        return self.table_counts.get(table, self.default_rows)

    def _pick_parent(self, ctx: SeedContext, parents: list[dict[str, Any]]) -> dict[str, Any]:
        if not parents:
            raise RuntimeError("No parent rows available for FK")
        if self.fk_distribution == "skewed":
            return skewed_choice(ctx, parents)
        if self.fk_distribution == "uniform":
            return ctx.rng.choice(parents)
        return zipf_choice(ctx, parents, alpha=1.15)

    def _fill_foreign_keys(
        self,
        ctx: SeedContext,
        node: TableNode,
        row: dict[str, Any],
        store: GeneratedStore,
    ) -> bool:
        # Prefer wider (composite) FKs first so product_id+warehouse_id stay paired
        edges = sorted(node.foreign_keys, key=lambda e: len(e.source_columns), reverse=True)

        for edge in edges:
            # Skip if all source columns already assigned (e.g. by a composite FK)
            if all(c in row for c in edge.source_columns):
                continue

            parents = store.parent_keys(edge.target_table)
            if not parents:
                if edge.nullable or edge.target_table == node.name:
                    for col in edge.source_columns:
                        if col not in row:
                            row[col] = None
                    continue
                return False

            # Self-referential: sometimes null (root), else pick earlier row
            if edge.target_table == node.name:
                existing = store.parent_keys(node.name)
                if not existing or ctx.rng.random() < 0.35:
                    for col in edge.source_columns:
                        if col not in row:
                            row[col] = None
                    continue
                parent = self._pick_parent(ctx, existing)
            else:
                parent = self._pick_parent(ctx, parents)

            for src, tgt in zip(edge.source_columns, edge.target_columns):
                if src not in row:
                    row[src] = parent[tgt]
        return True

    def _build_row(
        self,
        ctx: SeedContext,
        node: TableNode,
        index: int,
        store: GeneratedStore,
        tracker: ConstraintTracker,
    ) -> dict[str, Any] | None:
        row: dict[str, Any] = {}

        if not self._fill_foreign_keys(ctx, node, row, store):
            return None

        for col_name, col in node.columns.items():
            if col_name in row:
                continue
            # Let DB assign autoincrement PKs when possible; still need in-memory keys
            if col.primary_key and col.autoincrement and col.fk_target is None:
                # provisional negative id; replaced after flush if ORM used
                row[col_name] = -(index + 1)
                continue
            if col.nullable and ctx.rng.random() < 0.08 and not col.primary_key:
                row[col_name] = None
                continue
            row[col_name] = generate_scalar(ctx, col, index=index, table_name=node.name)

        row = apply_derived_checks(node, row)

        if self.row_hook:
            patched = self.row_hook(node.name, row, ctx)
            if patched is None:
                return None
            row = patched

        if not tracker.row_ok(node.unique_constraints + [node.primary_key], row):
            return None
        return row

    def generate_table(
        self,
        table_name: str,
        store: GeneratedStore,
        ctx: SeedContext | None = None,
    ) -> list[dict[str, Any]]:
        node = self.graph.tables[table_name]
        ctx = ctx or SeedContext(seed=self.seed).derive(table_name)
        tracker = ConstraintTracker()
        tracker.register_keys(node.unique_constraints + [node.primary_key])

        # Seed tracker with already-generated rows (self-FK / retries)
        for existing in store.rows.get(table_name, []):
            tracker.commit_row(node.unique_constraints + [node.primary_key], existing)

        target = self.count_for(table_name)
        created: list[dict[str, Any]] = []
        attempts = 0
        max_attempts = max(target * 40, 100)

        while len(created) < target and attempts < max_attempts:
            attempts += 1
            row = self._build_row(ctx, node, len(created), store, tracker)
            if row is None:
                continue
            tracker.commit_row(node.unique_constraints + [node.primary_key], row)
            store.add(table_name, row, node.primary_key)
            created.append(row)

        return created

    def generate_all(self, ctx: SeedContext | None = None) -> GeneratedStore:
        ctx = ctx or SeedContext(seed=self.seed)
        store = GeneratedStore()
        for table_name in self.graph.generation_order:
            table_ctx = ctx.derive(table_name)
            rows = self.generate_table(table_name, store, table_ctx)
            print(f"  {table_name}: {len(rows)} rows")
        return store

    def insert_all(self, session: Session, model_by_table: dict[str, type]) -> GeneratedStore:
        """
        Generate in FK order and INSERT via ORM.
        Replaces provisional autoincrement PKs with real DB ids and refreshes the key store.
        """
        ctx = SeedContext(seed=self.seed)
        store = GeneratedStore()

        for table_name in self.graph.generation_order:
            model = model_by_table.get(table_name)
            if model is None:
                print(f"  skip {table_name}: no ORM model mapped")
                continue

            node = self.graph.tables[table_name]
            table_ctx = ctx.derive(table_name)
            tracker = ConstraintTracker()
            tracker.register_keys(node.unique_constraints + [node.primary_key])

            target = self.count_for(table_name)
            created = 0
            attempts = 0
            max_attempts = max(target * 40, 100)
            auto_pk = [
                c for c in node.primary_key
                if node.columns[c].autoincrement and node.columns[c].fk_target is None
            ]

            while created < target and attempts < max_attempts:
                attempts += 1
                row = self._build_row(table_ctx, node, created, store, tracker)
                if row is None:
                    continue

                insert_payload = dict(row)
                for pk in auto_pk:
                    insert_payload.pop(pk, None)

                obj = model(**insert_payload)
                session.add(obj)
                try:
                    session.flush()
                except Exception:
                    session.rollback()
                    continue

                # Rebuild row with real PKs
                for pk in node.primary_key:
                    row[pk] = getattr(obj, pk)

                tracker.commit_row(node.unique_constraints + [node.primary_key], row)
                store.add(table_name, row, node.primary_key)
                created += 1

            print(f"  {table_name}: {created} rows")

        return store
