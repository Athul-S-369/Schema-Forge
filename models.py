"""SQLAlchemy ORM models for the amazon_marketplace schema."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass



class Country(Base):
    __tablename__ = "country"

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    iso_code: Mapped[str] = mapped_column(String(2), nullable=False, unique=True)

    states: Mapped[list["State"]] = relationship(back_populates="country")
    brands: Mapped[list["Brand"]] = relationship(back_populates="country")


class State(Base):
    __tablename__ = "state"
    __table_args__ = (
        UniqueConstraint("country_id", "name"),
        Index("idx_state_country", "country_id"),
    )

    state_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.country_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    country: Mapped["Country"] = relationship(back_populates="states")
    cities: Mapped[list["City"]] = relationship(back_populates="state")
    tax_rates: Mapped[list["TaxRate"]] = relationship(back_populates="state")


class City(Base):
    __tablename__ = "city"
    __table_args__ = (
        UniqueConstraint("state_id", "name"),
        Index("idx_city_state", "state_id"),
    )

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("state.state_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    state: Mapped["State"] = relationship(back_populates="cities")



class SettlementPolicy(Base):
    __tablename__ = "settlement_policy"
    __table_args__ = (
        CheckConstraint("frequency IN ('daily','weekly','biweekly')"),
        CheckConstraint("commission_pct BETWEEN 0 AND 100"),
    )

    policy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    commission_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    sellers: Mapped[list["Seller"]] = relationship(back_populates="policy")



class Seller(Base):
    __tablename__ = "seller"
    __table_args__ = (
        CheckConstraint("status IN ('active','suspended','under_review','inactive')"),
        Index("idx_seller_policy", "policy_id"),
        Index("idx_seller_status", "status"),
    )

    seller_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("settlement_policy.policy_id"), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    onboarded_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    tax_reg_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    policy: Mapped["SettlementPolicy"] = relationship(back_populates="sellers")
    products: Mapped[list["Product"]] = relationship(back_populates="seller")
    settlements: Mapped[list["Settlement"]] = relationship(back_populates="seller")



class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = (Index("idx_brand_country", "country_id"),)

    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("country.country_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)

    country: Mapped["Country"] = relationship(back_populates="brands")
    products: Mapped[list["Product"]] = relationship(back_populates="brand")



class Product(Base):
    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("price >= 0"),
        CheckConstraint("weight_kg > 0"),
        CheckConstraint("dim_l_cm > 0"),
        CheckConstraint("dim_w_cm > 0"),
        CheckConstraint("dim_h_cm > 0"),
        Index("idx_product_seller", "seller_id"),
        Index("idx_product_brand", "brand_id"),
        Index("idx_product_active", "is_active"),
    )

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.seller_id"), nullable=False)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.brand_id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    dim_l_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    dim_w_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    dim_h_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    listed_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    seller: Mapped["Seller"] = relationship(back_populates="products")
    brand: Mapped["Brand"] = relationship(back_populates="products")



class Category(Base):
    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("parent_id", "name"),
        Index("idx_category_parent", "parent_id"),
    )

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("category.category_id"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)


class ProductCategory(Base):
    __tablename__ = "product_category"
    __table_args__ = (Index("idx_pc_category", "category_id"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.category_id"), primary_key=True)



class ProductImage(Base):
    __tablename__ = "product_image"
    __table_args__ = (
        CheckConstraint("position >= 1"),
        UniqueConstraint("product_id", "position"),
        Index("idx_image_product", "product_id"),
    )

    image_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")



class StarLabel(Base):
    __tablename__ = "star_label"
    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5"),)

    stars: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)



class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (Index("idx_customer_email", "email"),)

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    pref_lang: Mapped[str] = mapped_column(String(5), nullable=False, server_default="en")


class CustomerAddress(Base):
    __tablename__ = "customer_address"
    __table_args__ = (
        Index("idx_addr_customer", "customer_id"),
        Index("idx_addr_city", "city_id"),
    )

    address_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id", ondelete="CASCADE"), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.city_id"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False, server_default="Home")
    street: Mapped[str] = mapped_column(String(300), nullable=False)
    locality: Mapped[str | None] = mapped_column(String(150))
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)



class PaymentMethod(Base):
    __tablename__ = "payment_method"
    __table_args__ = (
        CheckConstraint("type IN ('credit_card','debit_card','upi','wallet','netbanking','cod')"),
        Index("idx_pm_customer", "customer_id"),
    )

    pm_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_label: Mapped[str] = mapped_column(String(50), nullable=False)
    added_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())



class Cart(Base):
    __tablename__ = "cart"
    __table_args__ = (
        CheckConstraint("status IN ('active','converted','abandoned')"),
        Index("idx_cart_customer", "customer_id"),
        Index("idx_cart_status", "status"),
    )

    cart_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")


class CartItem(Base):
    __tablename__ = "cart_item"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        Index("idx_cart_item_product", "product_id"),
    )

    cart_id: Mapped[int] = mapped_column(ForeignKey("cart.cart_id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")



class Coupon(Base):
    __tablename__ = "coupon"
    __table_args__ = (
        CheckConstraint("discount_type IN ('percentage','flat')"),
        CheckConstraint("discount_value > 0"),
        CheckConstraint("valid_to >= valid_from"),
        Index("idx_coupon_code", "code"),
        Index("idx_coupon_validity", "valid_from", "valid_to"),
    )

    coupon_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)



class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('placed','packed','shipped','delivered','cancelled')"),
        CheckConstraint("total_amount >= 0"),
        Index("idx_order_customer", "customer_id"),
        Index("idx_order_status", "status"),
    )

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    address_id: Mapped[int] = mapped_column(ForeignKey("customer_address.address_id"), nullable=False)
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupon.coupon_id"))
    placed_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="placed")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)



class OrderLine(Base):
    __tablename__ = "order_line"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("unit_price >= 0"),
        CheckConstraint("line_total = quantity * unit_price"),
        UniqueConstraint("order_id", "product_id"),
        Index("idx_ol_order", "order_id"),
        Index("idx_ol_product", "product_id"),
    )

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)



class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("amount > 0"),
        CheckConstraint("status IN ('authorized','captured','failed','retried','refunded')"),
        Index("idx_payment_order", "order_id"),
        Index("idx_payment_pm", "pm_id"),
    )

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False)
    pm_id: Mapped[int | None] = mapped_column(ForeignKey("payment_method.pm_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class PaymentGatewayEvent(Base):
    __tablename__ = "payment_gateway_event"
    __table_args__ = (
        CheckConstraint("event_type IN ('authorized','captured','failed','retried','voided')"),
        Index("idx_pge_payment", "payment_id"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payment.payment_id"), nullable=False)
    gateway_ref: Mapped[str | None] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())



class Warehouse(Base):
    __tablename__ = "warehouse"
    __table_args__ = (
        CheckConstraint("capacity > 0"),
        Index("idx_warehouse_city", "city_id"),
    )

    warehouse_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.city_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    street: Mapped[str] = mapped_column(String(300), nullable=False)
    locality: Mapped[str | None] = mapped_column(String(150))
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)



class LogisticsPartner(Base):
    __tablename__ = "logistics_partner"
    __table_args__ = (CheckConstraint("sla_rating BETWEEN 0 AND 5"),)

    lp_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    sla_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    contact_no: Mapped[str | None] = mapped_column(String(20))



class Shipment(Base):
    __tablename__ = "shipment"
    __table_args__ = (
        UniqueConstraint("lp_id", "tracking_no"),
        Index("idx_shipment_order", "order_id"),
        Index("idx_shipment_warehouse", "warehouse_id"),
        Index("idx_shipment_lp", "lp_id"),
    )

    shipment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.warehouse_id"), nullable=False)
    lp_id: Mapped[int] = mapped_column(ForeignKey("logistics_partner.lp_id"), nullable=False)
    tracking_no: Mapped[str] = mapped_column(String(100), nullable=False)
    dispatched_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())


class ShipmentStatus(Base):
    __tablename__ = "shipment_status"
    __table_args__ = (
        CheckConstraint("status IN ('dispatched','in_transit','out_for_delivery','delivered','failed','returned')"),
        Index("idx_ss_shipment", "shipment_id"),
    )

    ss_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempt"
    __table_args__ = (
        CheckConstraint("outcome IN ('successful','customer_unavailable','address_issue','refused','other')"),
        Index("idx_da_shipment", "shipment_id"),
    )

    attempt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipment.shipment_id"), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)



class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("qty_on_hand >= 0"),
        Index("idx_inv_warehouse", "warehouse_id"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.warehouse_id"), primary_key=True)
    qty_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class InventoryMovement(Base):
    __tablename__ = "inventory_movement"
    __table_args__ = (
        CheckConstraint("movement_type IN ('inbound','reserved','outbound','return_to_stock','adjustment')"),
        CheckConstraint("quantity != 0"),
        ForeignKeyConstraint(
            ["product_id", "warehouse_id"],
            ["inventory.product_id", "inventory.warehouse_id"],
        ),
        Index("idx_im_product", "product_id"),
        Index("idx_im_warehouse", "warehouse_id"),
    )

    movement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.warehouse_id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    moved_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())



class ReturnReason(Base):
    __tablename__ = "return_reason"

    reason_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Return(Base):
    __tablename__ = "returns"
    __table_args__ = (
        UniqueConstraint("line_id"),
        Index("idx_return_line", "line_id"),
        Index("idx_return_reason", "reason_id"),
    )

    return_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("order_line.line_id"), nullable=False)
    reason_id: Mapped[int] = mapped_column(ForeignKey("return_reason.reason_id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())


class Refund(Base):
    __tablename__ = "refund"
    __table_args__ = (CheckConstraint("amount > 0"),)

    refund_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.return_id"), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    processed_at: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    is_full: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")



class TaxRate(Base):
    __tablename__ = "tax_rate"
    __table_args__ = (
        CheckConstraint("rate_pct BETWEEN 0 AND 100"),
        UniqueConstraint("state_id", "tax_category", "effective_from"),
        Index("idx_tax_state", "state_id"),
    )

    tax_rate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("state.state_id"), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(50), nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())

    state: Mapped["State"] = relationship(back_populates="tax_rates")



class Settlement(Base):
    __tablename__ = "settlement"
    __table_args__ = (
        CheckConstraint("gross_sales >= 0"),
        CheckConstraint("commission >= 0"),
        CheckConstraint("tax_deducted >= 0"),
        CheckConstraint("net_payout = gross_sales - commission - tax_deducted"),
        CheckConstraint("period_end >= period_start"),
        UniqueConstraint("seller_id", "period_start", "period_end"),
        Index("idx_settlement_seller", "seller_id"),
        Index("idx_settlement_period", "period_start", "period_end"),
    )

    settlement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("seller.seller_id"), nullable=False)
    tax_rate_id: Mapped[int] = mapped_column(ForeignKey("tax_rate.tax_rate_id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    gross_sales: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    tax_deducted: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    net_payout: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)

    seller: Mapped["Seller"] = relationship(back_populates="settlements")


class SettlementStatus(Base):
    __tablename__ = "settlement_status"
    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','paid','on_hold','failed')"),
        Index("idx_sst_settlement", "settlement_id"),
    )

    status_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlement.settlement_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())



class Review(Base):
    __tablename__ = "review"
    __table_args__ = (
        UniqueConstraint("product_id", "customer_id"),
        Index("idx_review_product", "product_id"),
        Index("idx_review_customer", "customer_id"),
    )

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.product_id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.customer_id"), nullable=False)
    stars: Mapped[int] = mapped_column(ForeignKey("star_label.stars"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
