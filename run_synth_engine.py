"""
Focused synth engine entrypoint (v1 pillars only).

Usage:
    python run_synth_engine.py --inspect
    python run_synth_engine.py --seed 42 --rows 10
    python run_synth_engine.py --seed 42 --rows 5 --dry-run

Environment:
    DATABASE_URL   mysql+pymysql://...
    CREATE_TABLES  true|false
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Base
from synth_engine import SynthEngine, build_schema_graph

load_dotenv()

DEFAULT_DATABASE_URL = "mysql+pymysql://root:@localhost/amazon_marketplace"

# Sensible defaults for a smoke run — override with --rows / --counts
DEFAULT_COUNTS = {
    "country": 3,
    "state": 8,
    "city": 16,
    "settlement_policy": 3,
    "seller": 10,
    "brand": 8,
    "product": 30,
    "category": 12,
    "product_category": 40,
    "product_image": 40,
    "star_label": 5,
    "customer": 20,
    "customer_address": 30,
    "payment_method": 25,
    "cart": 15,
    "cart_item": 30,
    "coupon": 8,
    "orders": 25,
    "order_line": 50,
    "payment": 25,
    "payment_gateway_event": 40,
    "warehouse": 6,
    "logistics_partner": 4,
    "shipment": 20,
    "shipment_status": 40,
    "delivery_attempt": 25,
    "inventory": 40,
    "inventory_movement": 30,
    "return_reason": 6,
    "returns": 10,
    "refund": 8,
    "tax_rate": 8,
    "settlement": 10,
    "settlement_status": 15,
    "review": 30,
}


def model_registry() -> dict[str, type]:
    registry: dict[str, type] = {}
    for name in dir(models):
        obj = getattr(models, name)
        if isinstance(obj, type) and hasattr(obj, "__tablename__"):
            registry[obj.__tablename__] = obj
    return registry


def parse_counts(raw: str | None, default_rows: int) -> dict[str, int]:
    counts = dict(DEFAULT_COUNTS)
    if default_rows:
        counts = {k: default_rows for k in counts}
        # Keep star_label fixed to 1..5 domain
        counts["star_label"] = 5
    if not raw:
        return counts
    for part in raw.split(","):
        table, _, value = part.partition("=")
        counts[table.strip()] = int(value.strip())
    return counts


def star_label_hook(table: str, row: dict, ctx):
    """star_label.stars must be the discrete 1..5 domain referenced by reviews."""
    if table != "star_label":
        return row
    labels = {1: "Poor", 2: "Fair", 3: "Average", 4: "Good", 5: "Excellent"}
    # index is encoded in provisional PK when autoincrement; use label uniqueness via stars
    used = getattr(star_label_hook, "_used", set())
    for stars in range(1, 6):
        if stars not in used:
            used.add(stars)
            star_label_hook._used = used
            row["stars"] = stars
            row["label"] = labels[stars]
            return row
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Focused schema-aware synthetic data engine")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed")
    parser.add_argument("--rows", type=int, default=0, help="Default rows per table (0 = profile defaults)")
    parser.add_argument(
        "--counts",
        type=str,
        default=None,
        help="Override counts: table=n,table=n",
    )
    parser.add_argument("--inspect", action="store_true", help="Print relationship graph and exit")
    parser.add_argument("--dry-run", action="store_true", help="Generate in memory only (no DB write)")
    parser.add_argument(
        "--fk-distribution",
        choices=("zipf", "skewed", "uniform"),
        default="zipf",
        help="How child rows pick parent FKs",
    )
    parser.add_argument("--dump", type=str, default=None, help="Write generated rows JSON to path (dry-run)")
    args = parser.parse_args()

    graph = build_schema_graph(Base)
    if args.inspect:
        print(graph.summarize())
        return

    counts = parse_counts(args.counts, args.rows)
    engine = SynthEngine.from_metadata(
        Base,
        seed=args.seed,
        table_counts=counts,
        fk_distribution=args.fk_distribution,
        row_hook=star_label_hook,
    )

    print(f"Seed={args.seed}  FK distribution={args.fk_distribution}")
    print(graph.summarize())
    print("\nGenerating...")

    if args.dry_run:
        # Reset star label hook state for clean run
        star_label_hook._used = set()
        store = engine.generate_all()
        if args.dump:
            with open(args.dump, "w", encoding="utf-8") as fh:
                json.dump(store.rows, fh, default=str, indent=2)
            print(f"Wrote {args.dump}")
        print("\nDry-run complete (no database writes).")
        return

    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    db = create_engine(url, echo=False)
    if os.getenv("CREATE_TABLES", "false").lower() in ("1", "true", "yes"):
        print("Creating tables...")
        Base.metadata.create_all(db)

    star_label_hook._used = set()
    SessionLocal = sessionmaker(bind=db)
    with SessionLocal() as session:
        try:
            engine.insert_all(session, model_registry())
            session.commit()
            print("\nSynthetic data inserted successfully.")
        except Exception as exc:
            session.rollback()
            print(f"\nError: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
