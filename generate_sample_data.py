"""
Generate sample data for the amazon_marketplace schema using SQLAlchemy.

Usage:
    python generate_sample_data.py

Environment variables (or .env file):
    DATABASE_URL  e.g. mysql+pymysql://root:password@localhost/amazon_marketplace
"""

from __future__ import annotations

import os
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from models import (
    Base,
    Brand,
    Cart,
    CartItem,
    Category,
    City,
    Country,
    Coupon,
    Customer,
    CustomerAddress,
    DeliveryAttempt,
    Inventory,
    InventoryMovement,
    LogisticsPartner,
    Order,
    OrderLine,
    Payment,
    PaymentGatewayEvent,
    PaymentMethod,
    Product,
    ProductCategory,
    ProductImage,
    Refund,
    Return,
    ReturnReason,
    Review,
    Seller,
    Settlement,
    SettlementPolicy,
    SettlementStatus,
    Shipment,
    ShipmentStatus,
    StarLabel,
    State,
    TaxRate,
    Warehouse,
)

load_dotenv()

DEFAULT_DATABASE_URL = "mysql+pymysql://root:@localhost/amazon_marketplace"

# Tune row counts here
COUNTS = {
    "countries": 3000,
    "states_per_country": 4000,
    "cities_per_state": 3000,
    "settlement_policies": 3000,
    "sellers": 8000,
    "brands": 12000,
    "products_per_seller": 5000,
    "root_categories": 6000,
    "subcategories_per_root": 3000,
    "customers": 25000,
    "addresses_per_customer": 2000,
    "payment_methods_per_customer": 2000,
    "carts": 15000,
    "coupons": 5000,
    "orders": 30000,
    "warehouses": 4000,
    "logistics_partners": 4000,
    "return_reasons": 5000,
    "reviews": 40000,
}

fake = Faker()
Faker.seed(42)
random.seed(42)


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_engine():
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return create_engine(url, echo=False)


def seed_star_labels(session: Session) -> None:
    existing = session.scalar(select(StarLabel).limit(1))
    if existing:
        return
    labels = [
        StarLabel(stars=1, label="Poor"),
        StarLabel(stars=2, label="Fair"),
        StarLabel(stars=3, label="Average"),
        StarLabel(stars=4, label="Good"),
        StarLabel(stars=5, label="Excellent"),
    ]
    session.add_all(labels)
    session.flush()


def seed_geography(session: Session) -> tuple[list[Country], list[State], list[City]]:
    geo_data = [
        ("India", "IN", ["Maharashtra", "Karnataka", "Delhi", "Tamil Nadu"]),
        ("United States", "US", ["California", "Texas", "New York", "Florida"]),
        ("United Kingdom", "GB", ["England", "Scotland", "Wales", "Northern Ireland"]),
    ]

    countries: list[Country] = []
    states: list[State] = []
    cities: list[City] = []

    for country_name, iso, state_names in geo_data[: COUNTS["countries"]]:
        country = Country(name=country_name, iso_code=iso)
        session.add(country)
        session.flush()
        countries.append(country)

        for state_name in state_names[: COUNTS["states_per_country"]]:
            state = State(country_id=country.country_id, name=state_name)
            session.add(state)
            session.flush()
            states.append(state)

            for _ in range(COUNTS["cities_per_state"]):
                city = City(state_id=state.state_id, name=fake.city())
                session.add(city)
                session.flush()
                cities.append(city)

    return countries, states, cities


def seed_settlement_policies(session: Session) -> list[SettlementPolicy]:
    policies_data = [
        ("Standard Weekly", "weekly", Decimal("12.00")),
        ("Premium Daily", "daily", Decimal("8.50")),
        ("Biweekly Starter", "biweekly", Decimal("15.00")),
    ]
    policies = [
        SettlementPolicy(name=name, frequency=freq, commission_pct=pct)
        for name, freq, pct in policies_data[: COUNTS["settlement_policies"]]
    ]
    session.add_all(policies)
    session.flush()
    return policies


def seed_sellers(session: Session, policies: list[SettlementPolicy]) -> list[Seller]:
    statuses = ["active", "active", "active", "under_review", "suspended", "inactive"]
    sellers = []
    for i in range(COUNTS["sellers"]):
        company = fake.company()
        seller = Seller(
            policy_id=random.choice(policies).policy_id,
            legal_name=f"{company} Pvt Ltd",
            display_name=company[:200],
            onboarded_at=fake.date_between(start_date="-3y", end_date="today"),
            email=f"seller{i + 1}@{fake.domain_name()}",
            phone=fake.numerify(text="+91##########"),
            status=random.choice(statuses),
            tax_reg_no=f"GSTIN{fake.numerify(text='##########')}{i}",
        )
        session.add(seller)
        sellers.append(seller)
    session.flush()
    return sellers


def seed_brands(session: Session, countries: list[Country]) -> list[Brand]:
    brands = []
    used_names: set[str] = set()
    for i in range(COUNTS["brands"]):
        name = fake.company()
        while name in used_names:
            name = fake.company()
        used_names.add(name)
        brand = Brand(
            country_id=random.choice(countries).country_id,
            name=name[:150],
        )
        session.add(brand)
        brands.append(brand)
    session.flush()
    return brands


def seed_products(session: Session, sellers: list[Seller], brands: list[Brand]) -> list[Product]:
    products = []
    for seller in sellers:
        for _ in range(COUNTS["products_per_seller"]):
            product = Product(
                seller_id=seller.seller_id,
                brand_id=random.choice(brands).brand_id,
                title=fake.catch_phrase()[:500],
                description=fake.paragraph(nb_sentences=3),
                price=money(random.uniform(99, 9999)),
                weight_kg=money(random.uniform(0.1, 15)),
                dim_l_cm=money(random.uniform(5, 80)),
                dim_w_cm=money(random.uniform(5, 60)),
                dim_h_cm=money(random.uniform(2, 40)),
                listed_at=fake.date_between(start_date="-2y", end_date="today"),
                is_active=random.random() > 0.1,
            )
            session.add(product)
            products.append(product)
    session.flush()
    return products


def seed_categories(session: Session) -> list[Category]:
    roots = ["Electronics", "Fashion", "Home & Kitchen", "Books", "Sports", "Beauty"]
    categories: list[Category] = []

    for root_name in roots[: COUNTS["root_categories"]]:
        root = Category(parent_id=None, name=root_name)
        session.add(root)
        session.flush()
        categories.append(root)

        for j in range(COUNTS["subcategories_per_root"]):
            sub = Category(parent_id=root.category_id, name=f"{root_name} - {fake.word().title()} {j + 1}")
            session.add(sub)
            session.flush()
            categories.append(sub)

    return categories


def seed_product_categories(session: Session, products: list[Product], categories: list[Category]) -> None:
    subcategories = [c for c in categories if c.parent_id is not None]
    for product in products:
        chosen = random.sample(subcategories, k=min(random.randint(1, 2), len(subcategories)))
        for cat in chosen:
            session.add(ProductCategory(product_id=product.product_id, category_id=cat.category_id))
    session.flush()


def seed_product_images(session: Session, products: list[Product]) -> None:
    for product in products:
        image_count = random.randint(1, 3)
        for pos in range(1, image_count + 1):
            session.add(
                ProductImage(
                    product_id=product.product_id,
                    url=f"https://picsum.photos/seed/{product.product_id}{pos}/800/600",
                    position=pos,
                    is_main=(pos == 1),
                )
            )
    session.flush()


def seed_customers(session: Session) -> list[Customer]:
    customers = []
    for i in range(COUNTS["customers"]):
        customer = Customer(
            full_name=fake.name(),
            email=f"customer{i + 1}@{fake.domain_name()}",
            phone=fake.numerify(text="+91##########"),
            joined_at=fake.date_between(start_date="-2y", end_date="today"),
            pref_lang=random.choice(["en", "en-IN", "hi", "ta", "kn"]),
        )
        session.add(customer)
        customers.append(customer)
    session.flush()
    return customers


def seed_customer_addresses(
    session: Session, customers: list[Customer], cities: list[City]
) -> list[CustomerAddress]:
    labels = ["Home", "Office", "Other"]
    addresses = []
    for customer in customers:
        for i in range(COUNTS["addresses_per_customer"]):
            addr = CustomerAddress(
                customer_id=customer.customer_id,
                city_id=random.choice(cities).city_id,
                label=labels[i % len(labels)],
                street=fake.street_address()[:300],
                locality=fake.city()[:150],
                postal_code=fake.postcode()[:20],
            )
            session.add(addr)
            addresses.append(addr)
    session.flush()
    return addresses


def seed_payment_methods(session: Session, customers: list[Customer]) -> list[PaymentMethod]:
    pm_types = ["credit_card", "debit_card", "upi", "wallet", "netbanking"]
    methods = []
    for customer in customers:
        for _ in range(COUNTS["payment_methods_per_customer"]):
            pm_type = random.choice(pm_types)
            if pm_type in ("credit_card", "debit_card"):
                label = f"**** {fake.numerify(text='####')}"
            elif pm_type == "upi":
                label = f"{fake.user_name()}@upi"
            else:
                label = f"{pm_type.title()} - {fake.word()}"
            pm = PaymentMethod(
                customer_id=customer.customer_id,
                type=pm_type,
                display_label=label[:50],
                added_at=fake.date_between(start_date="-1y", end_date="today"),
            )
            session.add(pm)
            methods.append(pm)
    session.flush()
    return methods


def seed_carts(session: Session, customers: list[Customer], products: list[Product]) -> None:
    statuses = ["active", "converted", "abandoned"]
    for i in range(COUNTS["carts"]):
        customer = random.choice(customers)
        cart = Cart(
            customer_id=customer.customer_id,
            created_at=fake.date_time_between(start_date="-6m", end_date="now"),
            status=random.choice(statuses),
        )
        session.add(cart)
        session.flush()

        for product in random.sample(products, k=random.randint(1, 3)):
            session.add(
                CartItem(
                    cart_id=cart.cart_id,
                    product_id=product.product_id,
                    quantity=random.randint(1, 3),
                )
            )
    session.flush()


def seed_coupons(session: Session) -> list[Coupon]:
    coupons = []
    today = date.today()
    for i in range(COUNTS["coupons"]):
        discount_type = random.choice(["percentage", "flat"])
        coupon = Coupon(
            code=f"SAVE{fake.numerify(text='####')}{i}",
            description=fake.sentence(),
            discount_type=discount_type,
            discount_value=money(10 if discount_type == "percentage" else random.uniform(50, 500)),
            valid_from=today - timedelta(days=random.randint(30, 90)),
            valid_to=today + timedelta(days=random.randint(30, 180)),
        )
        session.add(coupon)
        coupons.append(coupon)
    session.flush()
    return coupons


def seed_orders(
    session: Session,
    customers: list[Customer],
    addresses_by_customer: dict[int, list[CustomerAddress]],
    products: list[Product],
    coupons: list[Coupon],
) -> list[Order]:
    order_statuses = ["placed", "packed", "shipped", "delivered", "cancelled"]
    orders = []

    for _ in range(COUNTS["orders"]):
        customer = random.choice(customers)
        customer_addresses = addresses_by_customer[customer.customer_id]
        address = random.choice(customer_addresses)

        order_products = random.sample(products, k=random.randint(1, 4))
        lines_total = Decimal("0")
        line_specs = []
        for product in order_products:
            qty = random.randint(1, 3)
            unit_price = product.price
            line_total = money(qty * unit_price)
            lines_total += line_total
            line_specs.append((product, qty, unit_price, line_total))

        coupon = random.choice(coupons) if random.random() < 0.3 else None
        total = lines_total
        if coupon:
            if coupon.discount_type == "percentage":
                total = money(lines_total * (1 - coupon.discount_value / 100))
            else:
                total = money(max(Decimal("0"), lines_total - coupon.discount_value))

        order = Order(
            customer_id=customer.customer_id,
            address_id=address.address_id,
            coupon_id=coupon.coupon_id if coupon else None,
            placed_at=fake.date_time_between(start_date="-1y", end_date="now"),
            status=random.choice(order_statuses),
            total_amount=total,
        )
        session.add(order)
        session.flush()
        orders.append(order)

        for product, qty, unit_price, line_total in line_specs:
            session.add(
                OrderLine(
                    order_id=order.order_id,
                    product_id=product.product_id,
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

    session.flush()
    return orders


def seed_payments(
    session: Session,
    orders: list[Order],
    payment_methods_by_customer: dict[int, list[PaymentMethod]],
) -> list[Payment]:
    payment_statuses = ["authorized", "captured", "failed", "retried", "refunded"]
    payments = []

    for order in orders:
        if order.status == "cancelled" and random.random() < 0.5:
            continue

        customer_pms = payment_methods_by_customer.get(order.customer_id, [])
        pm = random.choice(customer_pms) if customer_pms and random.random() > 0.1 else None
        status = "captured" if order.status == "delivered" else random.choice(payment_statuses)

        payment = Payment(
            order_id=order.order_id,
            pm_id=pm.pm_id if pm else None,
            amount=order.total_amount,
            paid_at=order.placed_at + timedelta(minutes=random.randint(1, 60)),
            status=status,
        )
        session.add(payment)
        session.flush()
        payments.append(payment)

        session.add(
            PaymentGatewayEvent(
                payment_id=payment.payment_id,
                gateway_ref=f"GW-{fake.numerify(text='##########')}",
                event_type=status if status in ("authorized", "captured", "failed", "retried") else "captured",
                event_at=payment.paid_at,
            )
        )

        if status == "failed" and random.random() < 0.5:
            retry = Payment(
                order_id=order.order_id,
                pm_id=pm.pm_id if pm else None,
                amount=order.total_amount,
                paid_at=payment.paid_at + timedelta(hours=1),
                status="captured",
            )
            session.add(retry)
            session.flush()
            payments.append(retry)
            session.add(
                PaymentGatewayEvent(
                    payment_id=retry.payment_id,
                    gateway_ref=f"GW-{fake.numerify(text='##########')}",
                    event_type="retried",
                    event_at=retry.paid_at,
                )
            )

    session.flush()
    return payments


def seed_warehouses(session: Session, cities: list[City]) -> list[Warehouse]:
    warehouses = []
    for i in range(COUNTS["warehouses"]):
        wh = Warehouse(
            city_id=random.choice(cities).city_id,
            name=f"{fake.city()} Fulfillment Center",
            code=f"WH-{fake.lexify(text='???').upper()}{i + 1}",
            street=fake.street_address()[:300],
            locality=fake.city()[:150],
            postal_code=fake.postcode()[:20],
            capacity=random.randint(5000, 50000),
        )
        session.add(wh)
        warehouses.append(wh)
    session.flush()
    return warehouses


def seed_logistics_partners(session: Session) -> list[LogisticsPartner]:
    partners = []
    for i in range(COUNTS["logistics_partners"]):
        lp = LogisticsPartner(
            name=f"{fake.company()} Logistics {i + 1}",
            sla_rating=money(random.uniform(3.0, 5.0)),
            contact_no=fake.numerify(text="+91##########"),
        )
        session.add(lp)
        partners.append(lp)
    session.flush()
    return partners


def seed_shipments(
    session: Session,
    orders: list[Order],
    warehouses: list[Warehouse],
    partners: list[LogisticsPartner],
) -> list[Shipment]:
    shipments = []
    shipment_statuses = ["dispatched", "in_transit", "out_for_delivery", "delivered", "failed", "returned"]
    delivery_outcomes = ["successful", "customer_unavailable", "address_issue", "refused", "other"]

    for order in orders:
        if order.status in ("cancelled", "placed"):
            continue

        lp = random.choice(partners)
        shipment = Shipment(
            order_id=order.order_id,
            warehouse_id=random.choice(warehouses).warehouse_id,
            lp_id=lp.lp_id,
            tracking_no=f"TRK{fake.numerify(text='##########')}{order.order_id}",
            dispatched_at=order.placed_at.date() + timedelta(days=1),
        )
        session.add(shipment)
        session.flush()
        shipments.append(shipment)

        status_chain = random.sample(shipment_statuses[:4], k=random.randint(2, 4))
        if order.status == "delivered":
            status_chain.append("delivered")
        base_time = datetime.combine(shipment.dispatched_at, datetime.min.time())
        for j, status in enumerate(status_chain):
            session.add(
                ShipmentStatus(
                    shipment_id=shipment.shipment_id,
                    status=status,
                    updated_at=base_time + timedelta(days=j),
                )
            )

        if random.random() < 0.2:
            session.add(
                DeliveryAttempt(
                    shipment_id=shipment.shipment_id,
                    attempted_at=base_time + timedelta(days=len(status_chain)),
                    outcome=random.choice(delivery_outcomes),
                    note=fake.sentence() if random.random() < 0.5 else None,
                )
            )

    session.flush()
    return shipments


def seed_inventory(session: Session, products: list[Product], warehouses: list[Warehouse]) -> None:
    movement_types_out = ["reserved", "outbound"]

    for product in products:
        for warehouse in random.sample(warehouses, k=random.randint(1, len(warehouses))):
            qty = random.randint(10, 500)
            inv = Inventory(product_id=product.product_id, warehouse_id=warehouse.warehouse_id, qty_on_hand=qty)
            session.add(inv)
            session.flush()

            session.add(
                InventoryMovement(
                    product_id=product.product_id,
                    warehouse_id=warehouse.warehouse_id,
                    movement_type="inbound",
                    quantity=qty,
                    moved_at=fake.date_time_between(start_date="-6m", end_date="now"),
                )
            )

            if qty > 20:
                out_qty = random.randint(1, min(20, qty // 2))
                session.add(
                    InventoryMovement(
                        product_id=product.product_id,
                        warehouse_id=warehouse.warehouse_id,
                        movement_type=random.choice(movement_types_out),
                        quantity=-out_qty,
                        moved_at=fake.date_time_between(start_date="-3m", end_date="now"),
                    )
                )

    session.flush()


def seed_return_reasons(session: Session) -> list[ReturnReason]:
    reasons_data = [
        ("DAMAGED_ARRIVAL", "Product arrived damaged or broken"),
        ("WRONG_ITEM", "Received a different item than ordered"),
        ("SIZE_ISSUE", "Size or fit does not match expectations"),
        ("QUALITY_ISSUE", "Product quality below expectations"),
        ("CHANGED_MIND", "Customer no longer wants the product"),
    ]
    reasons = [
        ReturnReason(code=code, description=desc)
        for code, desc in reasons_data[: COUNTS["return_reasons"]]
    ]
    session.add_all(reasons)
    session.flush()
    return reasons


def seed_returns_and_refunds(
    session: Session,
    order_lines: list[OrderLine],
    reasons: list[ReturnReason],
) -> None:
    refund_methods = ["original_payment", "wallet", "bank_transfer"]
    eligible_lines = random.sample(order_lines, k=min(len(order_lines) // 10, 8))

    for line in eligible_lines:
        ret = Return(
            line_id=line.line_id,
            reason_id=random.choice(reasons).reason_id,
            raised_at=fake.date_time_between(start_date="-3m", end_date="now"),
        )
        session.add(ret)
        session.flush()

        session.add(
            Refund(
                return_id=ret.return_id,
                amount=line.line_total,
                processed_at=fake.date_between(start_date="-2m", end_date="today"),
                method=random.choice(refund_methods),
                is_full=random.random() > 0.2,
            )
        )

    session.flush()


def seed_tax_rates(session: Session, states: list[State]) -> list[TaxRate]:
    categories = ["standard", "digital_goods", "essential"]
    rates = []
    for state in states:
        for category in categories:
            rate = TaxRate(
                state_id=state.state_id,
                tax_category=category,
                rate_pct=money(random.uniform(5, 18)),
                effective_from=date.today() - timedelta(days=365),
            )
            session.add(rate)
            rates.append(rate)
    session.flush()
    return rates


def seed_settlements(
    session: Session,
    sellers: list[Seller],
    tax_rates: list[TaxRate],
    policies_by_id: dict[int, SettlementPolicy],
) -> None:
    settlement_statuses = ["pending", "processing", "paid", "on_hold", "failed"]

    for seller in sellers:
        policy = policies_by_id[seller.policy_id]
        tax_rate = random.choice(tax_rates)

        gross = money(random.uniform(10000, 500000))
        commission = money(gross * policy.commission_pct / 100)
        tax_deducted = money(gross * tax_rate.rate_pct / 100)
        net = money(gross - commission - tax_deducted)

        period_start = fake.date_between(start_date="-6m", end_date="-3m")
        period_end = period_start + timedelta(days=random.choice([7, 14, 30]))

        settlement = Settlement(
            seller_id=seller.seller_id,
            tax_rate_id=tax_rate.tax_rate_id,
            period_start=period_start,
            period_end=period_end,
            gross_sales=gross,
            commission=commission,
            tax_deducted=tax_deducted,
            net_payout=net,
        )
        session.add(settlement)
        session.flush()

        for status in random.sample(settlement_statuses, k=random.randint(1, 3)):
            session.add(
                SettlementStatus(
                    settlement_id=settlement.settlement_id,
                    status=status,
                    updated_at=fake.date_time_between(start_date="-3m", end_date="now"),
                )
            )

    session.flush()


def seed_reviews(session: Session, products: list[Product], customers: list[Customer]) -> None:
    used_pairs: set[tuple[int, int]] = set()
    created = 0

    while created < COUNTS["reviews"]:
        product = random.choice(products)
        customer = random.choice(customers)
        pair = (product.product_id, customer.customer_id)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)

        stars = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 20, 35, 30])[0]
        session.add(
            Review(
                product_id=product.product_id,
                customer_id=customer.customer_id,
                stars=stars,
                title=fake.sentence(nb_words=4)[:200],
                body=fake.paragraph(nb_sentences=2),
                created_at=fake.date_time_between(start_date="-1y", end_date="now"),
            )
        )
        created += 1

    session.flush()


def generate_all(session: Session) -> None:
    print("Seeding star labels...")
    seed_star_labels(session)

    print("Seeding geography...")
    countries, states, cities = seed_geography(session)

    print("Seeding settlement policies & sellers...")
    policies = seed_settlement_policies(session)
    policies_by_id = {p.policy_id: p for p in policies}
    sellers = seed_sellers(session, policies)

    print("Seeding brands & products...")
    brands = seed_brands(session, countries)
    products = seed_products(session, sellers, brands)

    print("Seeding categories & product images...")
    categories = seed_categories(session)
    seed_product_categories(session, products, categories)
    seed_product_images(session, products)

    print("Seeding customers...")
    customers = seed_customers(session)
    addresses = seed_customer_addresses(session, customers, cities)
    addresses_by_customer: dict[int, list[CustomerAddress]] = defaultdict(list)
    for addr in addresses:
        addresses_by_customer[addr.customer_id].append(addr)

    payment_methods = seed_payment_methods(session, customers)
    payment_methods_by_customer: dict[int, list[PaymentMethod]] = defaultdict(list)
    for pm in payment_methods:
        payment_methods_by_customer[pm.customer_id].append(pm)

    print("Seeding carts & coupons...")
    seed_carts(session, customers, products)
    coupons = seed_coupons(session)

    print("Seeding orders & payments...")
    orders = seed_orders(session, customers, addresses_by_customer, products, coupons)
    seed_payments(session, orders, payment_methods_by_customer)

    print("Seeding warehouses, logistics & shipments...")
    warehouses = seed_warehouses(session, cities)
    partners = seed_logistics_partners(session)
    seed_shipments(session, orders, warehouses, partners)

    print("Seeding inventory...")
    seed_inventory(session, products, warehouses)

    print("Seeding returns, tax rates & settlements...")
    order_lines = session.scalars(select(OrderLine)).all()
    reasons = seed_return_reasons(session)
    seed_returns_and_refunds(session, order_lines, reasons)
    tax_rates = seed_tax_rates(session, states)
    seed_settlements(session, sellers, tax_rates, policies_by_id)

    print("Seeding reviews...")
    seed_reviews(session, products, customers)


def main() -> None:
    engine = get_engine()
    create_tables = os.getenv("CREATE_TABLES", "false").lower() in ("1", "true", "yes")

    if create_tables:
        print("Creating tables (CREATE_TABLES=true)...")
        Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        try:
            generate_all(session)
            session.commit()
            print("\nSample data generated successfully.")
        except Exception as exc:
            session.rollback()
            print(f"\nError: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
