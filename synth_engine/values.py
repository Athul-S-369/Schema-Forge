"""Column value synthesis guided by schema + constraint hints + distributions."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .constraints import clamp_numeric
from .distributions import lognormal_positive, normal_int, weighted_enum
from .rng import SeedContext
from .schema import ColumnInfo, TableNode


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _truncate(text: str, length: int | None) -> str:
    if length is None:
        return text
    return text[:length]


def generate_scalar(
    ctx: SeedContext,
    column: ColumnInfo,
    *,
    index: int,
    table_name: str,
) -> Any:
    """Produce a non-FK scalar that respects type, length, enum, and numeric bounds."""
    if column.enum_values:
        # Skew toward earlier / "happier" statuses when present
        values = list(column.enum_values)
        if column.name in {"status", "outcome", "event_type", "movement_type", "frequency"}:
            weights = [max(0.05, 1.0 / (i + 1)) for i in range(len(values))]
            return weighted_enum(ctx, values, weights)
        return ctx.rng.choice(values)

    name = column.name.lower()
    t = column.type_name

    if t in {"Boolean"}:
        return ctx.rng.random() > 0.15

    if t in {"Integer", "SmallInteger", "BigInteger"}:
        lo, hi = (0, 100)
        if column.numeric_bounds:
            b_lo, b_hi = column.numeric_bounds
            lo = int(b_lo) if b_lo is not None else lo
            hi = int(b_hi) if b_hi is not None else hi
        if name == "quantity":
            hi = min(hi if column.numeric_bounds and column.numeric_bounds[1] is not None else 8, 8)
            lo = max(lo, 1)
            return normal_int(ctx, mean=2.0, std=1.2, low=lo, high=hi)
        if name in {"stars", "position"}:
            return normal_int(ctx, mean=(lo + hi) / 2, std=max(1.0, (hi - lo) / 4), low=lo, high=hi)
        if name == "capacity":
            return normal_int(ctx, mean=5000, std=1500, low=max(lo, 100), high=hi if hi > 100 else 20_000)
        return ctx.rng.randint(lo, max(lo, hi))

    if t in {"Numeric", "Float", "DECIMAL"}:
        lo = 0.01
        hi = 10_000.0
        if column.numeric_bounds:
            b_lo, b_hi = column.numeric_bounds
            if b_lo is not None:
                lo = float(b_lo)
            if b_hi is not None:
                hi = float(b_hi)
        # Prices / money-ish columns: lognormal; percentages: bounded normal
        if "pct" in name or "rate" in name or "commission" in name:
            mean = (lo + hi) / 2
            val = clamp_numeric(ctx.rng.gauss(mean, max(1.0, (hi - lo) / 6)), (lo, hi))
        else:
            val = lognormal_positive(ctx, mean=3.5, sigma=0.7, low=max(lo, 0.01), high=hi)
            val = clamp_numeric(val, (lo, hi))
        return money(val)

    if t in {"Date"}:
        start = date.today() - timedelta(days=365 * 3)
        end = date.today()
        delta = (end - start).days
        return start + timedelta(days=ctx.rng.randint(0, max(delta, 1)))

    if t in {"DateTime", "TIMESTAMP"}:
        start = datetime.now() - timedelta(days=365)
        end = datetime.now()
        span = int((end - start).total_seconds())
        return start + timedelta(seconds=ctx.rng.randint(0, max(span, 1)))

    if t in {"Text"}:
        return ctx.faker.paragraph(nb_sentences=2)

    # String / other
    if "email" in name:
        return _truncate(f"{table_name}_{index}_{ctx.faker.user_name()}@{ctx.faker.domain_name()}", column.length)
    if "phone" in name:
        return _truncate(ctx.faker.numerify(text="+91##########"), column.length)
    if "url" in name:
        return _truncate(f"https://picsum.photos/seed/{table_name}{index}/800/600", column.length)
    if name in {"iso_code"}:
        return _truncate(ctx.faker.country_code(), column.length or 2)
    if "name" in name or name in {"title", "label", "legal_name", "display_name"}:
        return _truncate(f"{ctx.faker.company()} {index}", column.length)
    if name in {"street", "code"}:
        return _truncate(ctx.faker.street_address(), column.length)
    if "description" in name or "body" in name:
        return _truncate(ctx.faker.paragraph(nb_sentences=2), column.length)

    return _truncate(f"{table_name}_{column.name}_{index}", column.length)


def apply_derived_checks(table: TableNode, row: dict[str, Any]) -> dict[str, Any]:
    """
    Fix common CHECK formulas the parser cannot invent (e.g. line_total = qty * price).
    Keeps generated rows valid without a full SQL CHECK evaluator.
    """
    compact = " ".join(table.check_sql).lower().replace(" ", "")
    cols = set(row)

    if "line_total" in cols and "quantity" in cols and "unit_price" in cols:
        if "line_total=quantity*unit_price" in compact:
            qty = Decimal(str(row["quantity"]))
            price = Decimal(str(row["unit_price"]))
            row["line_total"] = money(float(qty * price))

    if (
        "net_payout" in cols
        and "gross_sales" in cols
        and "commission" in cols
        and "tax_deducted" in cols
    ):
        if "net_payout=gross_sales-commission-tax_deducted" in compact:
            gross = Decimal(str(row["gross_sales"]))
            commission = Decimal(str(row["commission"]))
            tax = Decimal(str(row["tax_deducted"]))
            # Keep non-negative commission/tax under gross
            if commission + tax > gross:
                commission = money(float(gross) * 0.1)
                tax = money(float(gross) * 0.05)
                row["commission"] = commission
                row["tax_deducted"] = tax
            row["net_payout"] = money(float(gross - commission - tax))

    if "valid_from" in cols and "valid_to" in cols and row["valid_from"] and row["valid_to"]:
        if row["valid_to"] < row["valid_from"]:
            row["valid_to"] = row["valid_from"] + timedelta(days=30)

    if "period_start" in cols and "period_end" in cols and row["period_start"] and row["period_end"]:
        if row["period_end"] < row["period_start"]:
            row["period_end"] = row["period_start"] + timedelta(days=14)

    return row
