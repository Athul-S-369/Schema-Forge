"""
Schema understanding engine.

Introspect SQLAlchemy MetaData / DeclarativeBase into a relationship graph:
tables, columns, FKs, unique keys, and CHECK constraints — no hand-written
Faker rule sheet required for structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import CheckConstraint, MetaData, Table, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import ForeignKeyConstraint


@dataclass(frozen=True)
class ForeignKeyEdge:
    source_table: str
    source_columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]
    nullable: bool


@dataclass
class ColumnInfo:
    name: str
    type_name: str
    nullable: bool
    primary_key: bool
    unique: bool
    autoincrement: bool
    python_type: Any | None
    length: int | None = None
    enum_values: tuple[str, ...] | None = None
    numeric_bounds: tuple[float | None, float | None] | None = None
    fk_target: tuple[str, str] | None = None  # (table, column)


@dataclass
class TableNode:
    name: str
    columns: dict[str, ColumnInfo]
    primary_key: tuple[str, ...]
    foreign_keys: list[ForeignKeyEdge] = field(default_factory=list)
    unique_constraints: list[tuple[str, ...]] = field(default_factory=list)
    check_sql: list[str] = field(default_factory=list)
    depends_on: set[str] = field(default_factory=set)


@dataclass
class SchemaGraph:
    tables: dict[str, TableNode]
    generation_order: list[str]

    def summarize(self) -> str:
        lines = [
            f"Schema graph: {len(self.tables)} tables",
            f"Generation order: {' -> '.join(self.generation_order)}",
            "",
        ]
        for name in self.generation_order:
            node = self.tables[name]
            fk_bits = [
                f"{','.join(e.source_columns)}->{e.target_table}"
                for e in node.foreign_keys
            ]
            deps = ", ".join(sorted(node.depends_on)) or "-"
            lines.append(
                f"  {name}: pk={node.primary_key} deps=[{deps}] "
                f"fks=[{'; '.join(fk_bits) or '-'}] "
                f"checks={len(node.check_sql)} uniques={len(node.unique_constraints)}"
            )
        return "\n".join(lines)


_IN_RE = re.compile(
    r"(?P<col>\w+)\s+IN\s*\((?P<body>[^)]+)\)",
    re.IGNORECASE,
)
_BETWEEN_RE = re.compile(
    r"(?P<col>\w+)\s+BETWEEN\s+(?P<lo>-?\d+(?:\.\d+)?)\s+AND\s+(?P<hi>-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CMP_RE = re.compile(
    r"(?P<col>\w+)\s*(?P<op>>=|<=|>|<|=)\s*(?P<val>-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _strip_quotes(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] in "'\"" and token[-1] == token[0]:
        return token[1:-1]
    return token


def parse_check_constraints(sql_texts: list[str]) -> dict[str, dict[str, Any]]:
    """
    Extract per-column constraint hints from CHECK SQL.
    Returns {column: {"in": [...], "min": x, "max": y, "exclusive_min": bool, ...}}
    """
    hints: dict[str, dict[str, Any]] = {}

    def bucket(col: str) -> dict[str, Any]:
        return hints.setdefault(col.lower(), {})

    for sql in sql_texts:
        text = sql.strip()
        for match in _IN_RE.finditer(text):
            col = match.group("col").lower()
            body = match.group("body")
            values = tuple(_strip_quotes(p) for p in body.split(","))
            bucket(col)["in"] = values

        for match in _BETWEEN_RE.finditer(text):
            col = match.group("col").lower()
            b = bucket(col)
            b["min"] = float(match.group("lo"))
            b["max"] = float(match.group("hi"))

        for match in _CMP_RE.finditer(text):
            # Skip equality expressions that are row formulas (e.g. line_total = quantity * unit_price)
            if "*" in text[match.start() : match.end() + 20]:
                continue
            col = match.group("col").lower()
            op = match.group("op")
            val = float(match.group("val"))
            b = bucket(col)
            if op == ">=":
                b["min"] = val
            elif op == ">":
                b["min"] = val
                b["exclusive_min"] = True
            elif op == "<=":
                b["max"] = val
            elif op == "<":
                b["max"] = val
                b["exclusive_max"] = True

    return hints


def _column_info(table: Table, col) -> ColumnInfo:
    type_ = col.type
    type_name = type(type_).__name__
    length = getattr(type_, "length", None)
    python_type = None
    try:
        python_type = type_.python_type
    except (NotImplementedError, AttributeError):
        python_type = None

    fk_target = None
    for fk in col.foreign_keys:
        fk_target = (fk.column.table.name, fk.column.name)
        break

    return ColumnInfo(
        name=col.name,
        type_name=type_name,
        nullable=bool(col.nullable),
        primary_key=bool(col.primary_key),
        unique=bool(col.unique),
        autoincrement=bool(getattr(col, "autoincrement", False) is True),
        python_type=python_type,
        length=length,
        fk_target=fk_target,
    )


def _build_table_node(table: Table) -> TableNode:
    columns = {c.name: _column_info(table, c) for c in table.columns}
    pk = tuple(c.name for c in table.primary_key.columns)

    fks: list[ForeignKeyEdge] = []
    depends: set[str] = set()
    for fk_constraint in table.constraints:
        if not isinstance(fk_constraint, ForeignKeyConstraint):
            continue
        source_cols = tuple(el.parent.name for el in fk_constraint.elements)
        target_table = fk_constraint.elements[0].column.table.name
        target_cols = tuple(el.column.name for el in fk_constraint.elements)
        nullable = all(columns[c].nullable for c in source_cols)
        # Self-FK: still a dependency edge but handled specially in ordering
        edge = ForeignKeyEdge(
            source_table=table.name,
            source_columns=source_cols,
            target_table=target_table,
            target_columns=target_cols,
            nullable=nullable,
        )
        fks.append(edge)
        if target_table != table.name:
            depends.add(target_table)

    uniques: list[tuple[str, ...]] = []
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            uniques.append(tuple(c.name for c in constraint.columns))

    for col in table.columns:
        if col.unique and not col.primary_key:
            key = (col.name,)
            if key not in uniques:
                uniques.append(key)

    checks = [
        str(c.sqltext)
        for c in table.constraints
        if isinstance(c, CheckConstraint)
    ]

    # Apply CHECK-derived enum / bounds onto columns
    hints = parse_check_constraints(checks)
    for col_name, hint in hints.items():
        if col_name not in columns:
            continue
        info = columns[col_name]
        if "in" in hint:
            info.enum_values = tuple(str(v) for v in hint["in"])
        lo = hint.get("min")
        hi = hint.get("max")
        if lo is not None or hi is not None:
            if hint.get("exclusive_min") and lo is not None:
                lo = lo + (1 if info.type_name in {"Integer", "SmallInteger"} else 1e-3)
            if hint.get("exclusive_max") and hi is not None:
                hi = hi - (1 if info.type_name in {"Integer", "SmallInteger"} else 1e-3)
            info.numeric_bounds = (lo, hi)

    return TableNode(
        name=table.name,
        columns=columns,
        primary_key=pk,
        foreign_keys=fks,
        unique_constraints=uniques,
        check_sql=checks,
        depends_on=depends,
    )


def topological_order(tables: dict[str, TableNode]) -> list[str]:
    """Kahn sort so every non-self FK parent is generated before the child."""
    remaining = {name: set(node.depends_on) for name, node in tables.items()}
    # Drop unknown deps (shouldn't happen)
    for name in list(remaining):
        remaining[name] = {d for d in remaining[name] if d in tables}

    ordered: list[str] = []
    ready = sorted(n for n, deps in remaining.items() if not deps)

    while ready:
        name = ready.pop(0)
        ordered.append(name)
        for child, deps in remaining.items():
            if name in deps:
                deps.remove(name)
                if not deps and child not in ordered and child not in ready:
                    ready.append(child)
        ready.sort()

    if len(ordered) != len(tables):
        stuck = sorted(set(tables) - set(ordered))
        # Cycles (rare): append remaining in name order after parents we have
        ordered.extend(stuck)

    return ordered


def build_schema_graph(source: MetaData | type[DeclarativeBase] | DeclarativeBase) -> SchemaGraph:
    if isinstance(source, MetaData):
        metadata = source
    elif isinstance(source, type) and issubclass(source, DeclarativeBase):
        metadata = source.metadata
    elif isinstance(source, DeclarativeBase):
        metadata = source.metadata
    else:
        raise TypeError("source must be MetaData or DeclarativeBase")

    tables = {name: _build_table_node(table) for name, table in metadata.tables.items()}
    order = topological_order(tables)
    return SchemaGraph(tables=tables, generation_order=order)
