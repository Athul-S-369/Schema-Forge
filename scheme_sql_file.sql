use amazon_marketplace;
-- MySQL Workbench Conversion (improved pass)
-- Review remaining CHECK constraints and PostgreSQL-specific constructs if MySQL version rejects them.

-- ============================================================
-- AMAZON MARKETPLACE -- PRODUCTION DATABASE SCHEMA
-- PostgreSQL 15+
-- Design principles:
--   1. Every normalization decision is justified in comments.
--   2. All FK columns are indexed (not guaranteed by PG).
--   3. Lookup/enum tables are preferred over raw enum types
--      except for truly closed, stable value sets.
--   4. No data is duplicated across rows that would violate
--      2NF or 3NF -- every non-key attribute depends on the
--      whole key and nothing but the key.
--   5. All timestamps are TIMESTAMP (UTC-aware).
-- ============================================================

-- ============================================================
-- 0. EXTENSION
-- ============================================================


-- ============================================================
-- 1. GEOGRAPHY  (shared reference data)
-- ============================================================

-- DESIGN: Country -> State -> City is a strict hierarchy.
-- City names are NOT unique globally ("Springfield" exists in
-- many states), so city is always scoped to state_id.
-- Warehouses and customer addresses both reference city_id,
-- ensuring state/country are never duplicated in those rows
-- (3NF: state belongs to city, not to the address row).

CREATE TABLE country (
    country_id   INT AUTO_INCREMENT       PRIMARY KEY,
    name         VARCHAR(100) NOT NULL UNIQUE,
    iso_code     CHAR(2)      NOT NULL UNIQUE   -- ISO 3166-1 alpha-2
);

CREATE TABLE state (
    state_id     INT AUTO_INCREMENT       PRIMARY KEY,
    country_id   INT          NOT NULL REFERENCES country(country_id),
    name         VARCHAR(100) NOT NULL,
    UNIQUE (country_id, name)
);
CREATE INDEX idx_state_country ON state(country_id);

CREATE TABLE city (
    city_id      INT AUTO_INCREMENT       PRIMARY KEY,
    state_id     INT          NOT NULL REFERENCES state(state_id),
    name         VARCHAR(100) NOT NULL,
    UNIQUE (state_id, name)
);
CREATE INDEX idx_city_state ON city(state_id);


-- ============================================================
-- 2. SETTLEMENT POLICY  (seller payment rules)
-- ============================================================

-- DESIGN: frequency and commission_pct are attributes of the
-- POLICY, not the seller. Two sellers on the same policy must
-- always share the same frequency -- this lives here, not on
-- the seller row. Violating this would be a 2NF violation.

CREATE TABLE settlement_policy (
    policy_id      INT AUTO_INCREMENT        PRIMARY KEY,
    name           VARCHAR(80)   NOT NULL UNIQUE,  -- e.g. "Standard Weekly"
    frequency      VARCHAR(20)   NOT NULL CHECK (frequency IN ('daily','weekly','biweekly')),
    commission_pct NUMERIC(5,2)  NOT NULL CHECK (commission_pct BETWEEN 0 AND 100)
);


-- ============================================================
-- 3. SELLERS
-- ============================================================

-- CONSTRAINT: status is a closed set; using CHECK is
-- appropriate here as the set is small and stable.
-- tax_reg_no is UNIQUE because two sellers cannot share
-- a tax identity.

CREATE TABLE seller (
    seller_id    INT AUTO_INCREMENT       PRIMARY KEY,
    policy_id    INT          NOT NULL REFERENCES settlement_policy(policy_id),
    legal_name   VARCHAR(200) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    onboarded_at DATE         NOT NULL DEFAULT (CURRENT_DATE),
    email        VARCHAR(254) NOT NULL UNIQUE,
    phone        VARCHAR(20)  NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended','under_review','inactive')),
    tax_reg_no   VARCHAR(50)  NOT NULL UNIQUE
);
CREATE INDEX idx_seller_policy   ON seller(policy_id);
CREATE INDEX idx_seller_status   ON seller(status);


-- ============================================================
-- 4. BRANDS
-- ============================================================

-- DESIGN: Brand name and country_of_origin are facts about the
-- brand itself, not about any product. Storing them here and
-- referencing brand_id from product eliminates repeating the
-- same string in thousands of product rows (3NF).

CREATE TABLE brand (
    brand_id   INT AUTO_INCREMENT       PRIMARY KEY,
    country_id INT          NOT NULL REFERENCES country(country_id),
    name       VARCHAR(150) NOT NULL UNIQUE
);
CREATE INDEX idx_brand_country ON brand(country_id);


-- ============================================================
-- 5. PRODUCTS
-- ============================================================

-- DESIGN: price here is the CURRENT listing price. The
-- historical price at order time is stored in order_line.
-- This separates mutable catalog data from immutable
-- transactional data -- a critical distinction at scale.
-- Weight and dimensions are intrinsic product facts, not
-- order-specific, so they live here.

CREATE TABLE product (
    product_id  INT AUTO_INCREMENT         PRIMARY KEY,
    seller_id   INT            NOT NULL REFERENCES seller(seller_id),
    brand_id    INT            NOT NULL REFERENCES brand(brand_id),
    title       VARCHAR(500)   NOT NULL,
    description TEXT,
    price       NUMERIC(12,2)  NOT NULL CHECK (price >= 0),
    weight_kg   NUMERIC(8,3)   CHECK (weight_kg > 0),
    dim_l_cm    NUMERIC(8,2)   CHECK (dim_l_cm > 0),
    dim_w_cm    NUMERIC(8,2)   CHECK (dim_w_cm > 0),
    dim_h_cm    NUMERIC(8,2)   CHECK (dim_h_cm > 0),
    listed_at   DATE           NOT NULL DEFAULT (CURRENT_DATE),
    is_active   BOOLEAN        NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_product_seller ON product(seller_id);
CREATE INDEX idx_product_brand  ON product(brand_id);
CREATE INDEX idx_product_active ON product(is_active);


-- ============================================================
-- 6. CATEGORIES  (self-referencing hierarchy)
-- ============================================================

-- DESIGN: parent_id is nullable -- top-level categories have
-- no parent. The hierarchy is a simple adjacency list. For
-- deep traversal queries use a recursive CTE (WITH RECURSIVE).
-- No depth limit is enforced at the schema level; business
-- logic should cap it.

CREATE TABLE category (
    category_id  INT AUTO_INCREMENT       PRIMARY KEY,
    parent_id    INT          REFERENCES category(category_id),  -- NULL = root
    name         VARCHAR(150) NOT NULL,
    UNIQUE (parent_id, name)   -- sibling names must be unique under the same parent
);
CREATE INDEX idx_category_parent ON category(parent_id);


-- DESIGN: A product can belong to MULTIPLE categories simultaneously
-- (many-to-many). The junction table product_category carries no
-- extra attributes -- the relationship itself is the fact.
-- PK is the composite (product_id, category_id) to prevent duplicates.

CREATE TABLE product_category (
    product_id   INT NOT NULL REFERENCES product(product_id) ON DELETE CASCADE,
    category_id  INT NOT NULL REFERENCES category(category_id),
    PRIMARY KEY (product_id, category_id)
);
CREATE INDEX idx_pc_category ON product_category(category_id);


-- ============================================================
-- 7. PRODUCT IMAGES
-- ============================================================

-- CONSTRAINT: position must be >= 1. is_main enforced at the
-- application layer (only one main image per product), or via
-- a partial unique index.

CREATE TABLE product_image (
    image_id    INT AUTO_INCREMENT        PRIMARY KEY,
    product_id  INT           NOT NULL REFERENCES product(product_id) ON DELETE CASCADE,
    url         TEXT          NOT NULL,
    position    SMALLINT      NOT NULL DEFAULT 1 CHECK (position >= 1),
    is_main     BOOLEAN       NOT NULL DEFAULT FALSE,
    UNIQUE (product_id, position)
);
-- Removed PostgreSQL partial unique index; enforce in application layer.
    -- enforces: at most one main image per product
CREATE INDEX idx_image_product ON product_image(product_id);


-- ============================================================
-- 8. STAR LABELS  (lookup table for review ratings)
-- ============================================================

-- DESIGN: The label for a given star count (e.g. 5 -> "Excellent")
-- is invariant -- the same everywhere. Storing it in a lookup
-- table eliminates repeating the string in every review row
-- and makes it a single source of truth. PK is the rating
-- value itself (1-5), so no surrogate key is needed.

CREATE TABLE star_label (
    stars  SMALLINT    PRIMARY KEY CHECK (stars BETWEEN 1 AND 5),
    label  VARCHAR(20) NOT NULL UNIQUE
);
INSERT INTO star_label VALUES
    (1,'Poor'),(2,'Fair'),(3,'Average'),(4,'Good'),(5,'Excellent');


-- ============================================================
-- 9. CUSTOMERS
-- ============================================================

CREATE TABLE customer (
    customer_id  INT AUTO_INCREMENT       PRIMARY KEY,
    full_name    VARCHAR(200) NOT NULL,
    email        VARCHAR(254) NOT NULL UNIQUE,
    phone        VARCHAR(20)  NOT NULL,
    joined_at    DATE         NOT NULL DEFAULT (CURRENT_DATE),
    pref_lang    CHAR(5)      NOT NULL DEFAULT 'en'   -- BCP-47 language tag
);
CREATE INDEX idx_customer_email ON customer(email);


-- ============================================================
-- 10. CUSTOMER ADDRESSES
-- ============================================================

-- DESIGN: Address rows reference city_id. State and country
-- are derived through city -> state -> country. Storing them
-- again on the address row would violate 3NF. Many customers
-- in the same city share city_id.

CREATE TABLE customer_address (
    address_id   INT AUTO_INCREMENT       PRIMARY KEY,
    customer_id  INT          NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE,
    city_id      INT          NOT NULL REFERENCES city(city_id),
    label        VARCHAR(50)  NOT NULL DEFAULT 'Home',  -- e.g. "Home", "Office"
    street       VARCHAR(300) NOT NULL,
    locality     VARCHAR(150),
    postal_code  VARCHAR(20)  NOT NULL
);
CREATE INDEX idx_addr_customer ON customer_address(customer_id);
CREATE INDEX idx_addr_city     ON customer_address(city_id);


-- ============================================================
-- 11. PAYMENT METHODS  (stored for convenience)
-- ============================================================

-- DESIGN: display_label stores masked info only (last 4 digits,
-- UPI handle). No raw card numbers are stored here -- PCI-DSS.

CREATE TABLE payment_method (
    pm_id          INT AUTO_INCREMENT      PRIMARY KEY,
    customer_id    INT         NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE,
    type           VARCHAR(30) NOT NULL CHECK (type IN ('credit_card','debit_card','upi','wallet','netbanking','cod')),
    display_label  VARCHAR(50) NOT NULL,
    added_at       DATE        NOT NULL DEFAULT (CURRENT_DATE)
);
CREATE INDEX idx_pm_customer ON payment_method(customer_id);


-- ============================================================
-- 12. CARTS
-- ============================================================

-- DESIGN: A cart belongs to one customer. Status tracks its
-- lifecycle. When converted, the order_id linkage lives on
-- the order row (order references customer, not cart) to
-- keep the cart/order relationship loose -- a cart may be
-- abandoned with no corresponding order.

CREATE TABLE cart (
    cart_id     INT AUTO_INCREMENT      PRIMARY KEY,
    customer_id INT         NOT NULL REFERENCES customer(customer_id),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','converted','abandoned'))
);
CREATE INDEX idx_cart_customer ON cart(customer_id);
CREATE INDEX idx_cart_status   ON cart(status);

CREATE TABLE cart_item (
    cart_id     INT     NOT NULL REFERENCES cart(cart_id) ON DELETE CASCADE,
    product_id  INT     NOT NULL REFERENCES product(product_id),
    quantity    INT     NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)
);
CREATE INDEX idx_cart_item_product ON cart_item(product_id);


-- ============================================================
-- 13. COUPONS
-- ============================================================

-- CONSTRAINT: valid_to must be after valid_from.
-- discount_type is a closed set.

CREATE TABLE coupon (
    coupon_id      INT AUTO_INCREMENT        PRIMARY KEY,
    code           VARCHAR(50)   NOT NULL UNIQUE,
    description    TEXT,
    discount_type  VARCHAR(10)   NOT NULL CHECK (discount_type IN ('percentage','flat')),
    discount_value NUMERIC(10,2) NOT NULL CHECK (discount_value > 0),
    valid_from     DATE          NOT NULL,
    valid_to       DATE          NOT NULL,
    CHECK (valid_to >= valid_from)
);
CREATE INDEX idx_coupon_code ON coupon(code);
CREATE INDEX idx_coupon_validity ON coupon(valid_from, valid_to);


-- ============================================================
-- 14. ORDERS
-- ============================================================

-- DESIGN: coupon_id is nullable -- most orders have no coupon.
-- total_amount is stored (denormalized) for fast retrieval;
-- it should always equal SUM(order_line.line_total) minus
-- any coupon discount. The application is responsible for
-- consistency; a check trigger can enforce it if needed.
-- address_id is the delivery address at time of order --
-- if the customer later deletes the address, the order
-- still retains the reference (ON DELETE RESTRICT).

CREATE TABLE orders (
    order_id     INT AUTO_INCREMENT        PRIMARY KEY,
    customer_id  INT           NOT NULL REFERENCES customer(customer_id),
    address_id   INT           NOT NULL REFERENCES customer_address(address_id),
    coupon_id    INT           REFERENCES coupon(coupon_id),
    placed_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(20)   NOT NULL DEFAULT 'placed'
                     CHECK (status IN ('placed','packed','shipped','delivered','cancelled')),
    total_amount NUMERIC(14,2) NOT NULL CHECK (total_amount >= 0)
);
CREATE INDEX idx_order_customer ON orders(customer_id);
CREATE INDEX idx_order_placed   ON orders(placed_at DESC);
CREATE INDEX idx_order_status   ON orders(status);
-- Removed PostgreSQL partial index on coupon_id.


-- ============================================================
-- 15. ORDER LINES
-- ============================================================

-- DESIGN: unit_price captures the price AT THE MOMENT of
-- purchase. This is critical -- the seller may change
-- product.price later, but the order must remember what
-- was actually charged. Storing it here is correct and
-- intentional (not a normalization violation).
-- line_total = quantity * unit_price, stored for query
-- efficiency. A CHECK constraint enforces consistency.
-- product_id is NOT NULL because the order line must always
-- refer to the product that was bought.

CREATE TABLE order_line (
    line_id      INT AUTO_INCREMENT        PRIMARY KEY,
    order_id     INT           NOT NULL REFERENCES orders(order_id),
    product_id   INT           NOT NULL REFERENCES product(product_id),
    quantity     INT           NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    line_total   NUMERIC(14,2) NOT NULL,
    CHECK (line_total = quantity * unit_price),
    UNIQUE (order_id, product_id)   -- same product cannot appear twice in one order
);
CREATE INDEX idx_ol_order   ON order_line(order_id);
CREATE INDEX idx_ol_product ON order_line(product_id);


-- ============================================================
-- 16. PAYMENTS & GATEWAY EVENTS
-- ============================================================

-- DESIGN: One order may trigger multiple payment attempts
-- (failure -> retry -> success). Each attempt is a row in
-- payment. Each attempt may have multiple gateway interactions
-- (authorized, captured, failed) recorded in payment_gateway_event.
-- This gives a full audit trail without ambiguity.

CREATE TABLE payment (
    payment_id   INT AUTO_INCREMENT        PRIMARY KEY,
    order_id     INT           NOT NULL REFERENCES orders(order_id),
    pm_id        INT           REFERENCES payment_method(pm_id),  -- nullable for COD
    amount       NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    paid_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(20)   NOT NULL
                     CHECK (status IN ('authorized','captured','failed','retried','refunded'))
);
CREATE INDEX idx_payment_order ON payment(order_id);
CREATE INDEX idx_payment_pm    ON payment(pm_id);

CREATE TABLE payment_gateway_event (
    event_id     INT AUTO_INCREMENT      PRIMARY KEY,
    payment_id   INT         NOT NULL REFERENCES payment(payment_id),
    gateway_ref  VARCHAR(100),              -- external transaction ID from gateway
    event_type   VARCHAR(20) NOT NULL
                     CHECK (event_type IN ('authorized','captured','failed','retried','voided')),
    event_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_pge_payment ON payment_gateway_event(payment_id);
CREATE INDEX idx_pge_time    ON payment_gateway_event(event_at DESC);


-- ============================================================
-- 17. WAREHOUSES
-- ============================================================

-- DESIGN: Warehouses reference city_id for the same reason
-- customer addresses do -- state/country are derived via the
-- geography hierarchy, never stored redundantly.
-- code is unique (used as a short warehouse identifier).

CREATE TABLE warehouse (
    warehouse_id  INT AUTO_INCREMENT       PRIMARY KEY,
    city_id       INT          NOT NULL REFERENCES city(city_id),
    name          VARCHAR(150) NOT NULL,
    code          VARCHAR(20)  NOT NULL UNIQUE,
    street        VARCHAR(300) NOT NULL,
    locality      VARCHAR(150),
    postal_code   VARCHAR(20)  NOT NULL,
    capacity      INT          NOT NULL CHECK (capacity > 0)  -- total storage units
);
CREATE INDEX idx_warehouse_city ON warehouse(city_id);


-- ============================================================
-- 18. LOGISTICS PARTNERS
-- ============================================================

-- DESIGN: sla_rating, name, and contact_no are facts about
-- the partner entity. They do not vary per shipment, so they
-- live here. Copying them onto each shipment row would violate 3NF.

CREATE TABLE logistics_partner (
    lp_id       INT AUTO_INCREMENT        PRIMARY KEY,
    name        VARCHAR(150)  NOT NULL UNIQUE,
    sla_rating  NUMERIC(3,1)  CHECK (sla_rating BETWEEN 0 AND 5),
    contact_no  VARCHAR(20)
);


-- ============================================================
-- 19. SHIPMENTS & STATUS UPDATES
-- ============================================================

-- DESIGN: An order may generate multiple shipments (partial
-- fulfilment from different warehouses). Each shipment has
-- one source warehouse and one logistics partner.
-- tracking_no is UNIQUE per logistics partner (not globally,
-- since different couriers may reuse numbers -- modelled as
-- UNIQUE per lp_id + tracking_no pair).

CREATE TABLE shipment (
    shipment_id   INT AUTO_INCREMENT      PRIMARY KEY,
    order_id      INT         NOT NULL REFERENCES orders(order_id),
    warehouse_id  INT         NOT NULL REFERENCES warehouse(warehouse_id),
    lp_id         INT         NOT NULL REFERENCES logistics_partner(lp_id),
    tracking_no   VARCHAR(100) NOT NULL,
    dispatched_at DATE        NOT NULL DEFAULT (CURRENT_DATE),
    UNIQUE (lp_id, tracking_no)
);
CREATE INDEX idx_shipment_order     ON shipment(order_id);
CREATE INDEX idx_shipment_warehouse ON shipment(warehouse_id);
CREATE INDEX idx_shipment_lp        ON shipment(lp_id);

-- DESIGN: Status history is append-only -- each update is a
-- new row with a timestamp. The current status is the most
-- recent row by updated_at. This preserves the full journey.

CREATE TABLE shipment_status (
    ss_id        INT AUTO_INCREMENT      PRIMARY KEY,
    shipment_id  INT         NOT NULL REFERENCES shipment(shipment_id),
    status       VARCHAR(30) NOT NULL
                     CHECK (status IN ('dispatched','in_transit','out_for_delivery','delivered','failed','returned')),
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ss_shipment ON shipment_status(shipment_id);
CREATE INDEX idx_ss_time     ON shipment_status(updated_at DESC);

CREATE TABLE delivery_attempt (
    attempt_id    INT AUTO_INCREMENT      PRIMARY KEY,
    shipment_id   INT         NOT NULL REFERENCES shipment(shipment_id),
    attempted_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    outcome       VARCHAR(30) NOT NULL
                      CHECK (outcome IN ('successful','customer_unavailable','address_issue','refused','other')),
    note          TEXT
);
CREATE INDEX idx_da_shipment ON delivery_attempt(shipment_id);


-- ============================================================
-- 20. INVENTORY
-- ============================================================

-- DESIGN: inventory holds the CURRENT on-hand quantity per
-- (product, warehouse) pair. qty_on_hand can be 0 but never
-- negative (CONSTRAINT). inventory_movement is the immutable
-- ledger from which qty_on_hand is derived; the two must be
-- kept in sync (application responsibility, or via trigger).

CREATE TABLE inventory (
    product_id    INT  NOT NULL REFERENCES product(product_id),
    warehouse_id  INT  NOT NULL REFERENCES warehouse(warehouse_id),
    qty_on_hand   INT  NOT NULL DEFAULT 0 CHECK (qty_on_hand >= 0),
    PRIMARY KEY (product_id, warehouse_id)
);
CREATE INDEX idx_inv_warehouse ON inventory(warehouse_id);

CREATE TABLE inventory_movement (
    movement_id    INT AUTO_INCREMENT      PRIMARY KEY,
    product_id     INT         NOT NULL REFERENCES product(product_id),
    warehouse_id   INT         NOT NULL REFERENCES warehouse(warehouse_id),
    movement_type  VARCHAR(20) NOT NULL
                       CHECK (movement_type IN ('inbound','reserved','outbound','return_to_stock','adjustment')),
    quantity       INT         NOT NULL CHECK (quantity != 0),  -- positive = in, negative = out
    moved_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id, warehouse_id) REFERENCES inventory(product_id, warehouse_id)
);
CREATE INDEX idx_im_product   ON inventory_movement(product_id);
CREATE INDEX idx_im_warehouse ON inventory_movement(warehouse_id);
CREATE INDEX idx_im_time      ON inventory_movement(moved_at DESC);


-- ============================================================
-- 21. RETURNS & REFUNDS
-- ============================================================

-- DESIGN: A return is raised against an order_line, not the
-- whole order. return_reason is a lookup table -- the same
-- reason code and description are reused across all returns,
-- so they live in a separate table (3NF).

CREATE TABLE return_reason (
    reason_id    INT AUTO_INCREMENT      PRIMARY KEY,
    code         VARCHAR(30) NOT NULL UNIQUE,  -- e.g. "DAMAGED_ARRIVAL"
    description  TEXT        NOT NULL
);

CREATE TABLE returns (
    return_id   INT AUTO_INCREMENT      PRIMARY KEY,
    line_id     INT         NOT NULL REFERENCES order_line(line_id),
    reason_id   INT         NOT NULL REFERENCES return_reason(reason_id),
    raised_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (line_id)   -- each order line can be returned at most once
);
CREATE INDEX idx_return_line   ON returns(line_id);
CREATE INDEX idx_return_reason ON returns(reason_id);

-- DESIGN: refund is 1:1 with return (one return -> one refund).
-- method is where the money goes back to.
-- is_full distinguishes partial from full refunds.

CREATE TABLE refund (
    refund_id     INT AUTO_INCREMENT        PRIMARY KEY,
    return_id     INT           NOT NULL UNIQUE REFERENCES returns(return_id),
    amount        NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    processed_at  DATE          NOT NULL DEFAULT (CURRENT_DATE),
    method        VARCHAR(30)   NOT NULL CHECK (method IN ('original_payment','wallet','bank_transfer')),
    is_full       BOOLEAN       NOT NULL DEFAULT TRUE
);


-- ============================================================
-- 22. TAX RATES
-- ============================================================

-- DESIGN: Tax rate is a function of (state, tax_category),
-- NOT of each individual settlement. Storing it centrally and
-- referencing tax_rate_id from settlement ensures that if a
-- rate changes, it only changes in one place (though for
-- historical accuracy, existing settlements should continue
-- to reference the rate that was in effect at that time --
-- consider versioning by date range for production).

CREATE TABLE tax_rate (
    tax_rate_id   INT AUTO_INCREMENT        PRIMARY KEY,
    state_id      INT           NOT NULL REFERENCES state(state_id),
    tax_category  VARCHAR(50)   NOT NULL,     -- e.g. "standard", "digital_goods"
    rate_pct      NUMERIC(5,2)  NOT NULL CHECK (rate_pct BETWEEN 0 AND 100),
    effective_from DATE         NOT NULL DEFAULT (CURRENT_DATE),
    UNIQUE (state_id, tax_category, effective_from)
);
CREATE INDEX idx_tax_state ON tax_rate(state_id);


-- ============================================================
-- 23. SELLER SETTLEMENTS
-- ============================================================

-- DESIGN: gross_sales, commission, tax_deducted, and net_payout
-- are stored on the settlement row as calculated snapshots for
-- that period. They are computed from order data at settlement
-- time and must not be recomputed on every query (too expensive
-- at scale). commission is derived from settlement_policy via
-- seller -- we cross-reference tax_rate_id for the rate used.
-- net_payout = gross_sales - commission - tax_deducted.
-- A CHECK constraint enforces this relationship.

CREATE TABLE settlement (
    settlement_id  INT AUTO_INCREMENT        PRIMARY KEY,
    seller_id      INT           NOT NULL REFERENCES seller(seller_id),
    tax_rate_id    INT           NOT NULL REFERENCES tax_rate(tax_rate_id),
    period_start   DATE          NOT NULL,
    period_end     DATE          NOT NULL,
    gross_sales    NUMERIC(16,2) NOT NULL CHECK (gross_sales >= 0),
    commission     NUMERIC(16,2) NOT NULL CHECK (commission >= 0),
    tax_deducted   NUMERIC(16,2) NOT NULL CHECK (tax_deducted >= 0),
    net_payout     NUMERIC(16,2) NOT NULL,
    CHECK (net_payout = gross_sales - commission - tax_deducted),
    CHECK (period_end >= period_start),
    UNIQUE (seller_id, period_start, period_end)
);
CREATE INDEX idx_settlement_seller ON settlement(seller_id);
CREATE INDEX idx_settlement_period ON settlement(period_start, period_end);

-- DESIGN: Settlement status is a lifecycle (pending -> processing
-- -> paid | on_hold). Each change is a timestamped row, giving
-- a full audit trail. Current status = latest updated_at.

CREATE TABLE settlement_status (
    status_id      INT AUTO_INCREMENT      PRIMARY KEY,
    settlement_id  INT         NOT NULL REFERENCES settlement(settlement_id),
    status         VARCHAR(20) NOT NULL
                       CHECK (status IN ('pending','processing','paid','on_hold','failed')),
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_sst_settlement ON settlement_status(settlement_id);
CREATE INDEX idx_sst_time       ON settlement_status(updated_at DESC);


-- ============================================================
-- 24. REVIEWS  (placed after customer + product + star_label)
-- ============================================================

-- DESIGN: One customer can review a product at most once
-- (unique constraint). stars is a FK to star_label, ensuring
-- only valid values (1-5) are stored and the label is always
-- consistent without being duplicated in the review row.

CREATE TABLE review (
    review_id    INT AUTO_INCREMENT        PRIMARY KEY,
    product_id   INT           NOT NULL REFERENCES product(product_id),
    customer_id  INT           NOT NULL REFERENCES customer(customer_id),
    stars        SMALLINT      NOT NULL REFERENCES star_label(stars),
    title        VARCHAR(200),
    body         TEXT,
    created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_id, customer_id)
);
CREATE INDEX idx_review_product  ON review(product_id);
CREATE INDEX idx_review_customer ON review(customer_id);


-- ============================================================
-- END OF SCHEMA
-- ============================================================
-- TABLE COUNT: 35 tables
-- Normalized to 3NF throughout; intentional denormalizations
-- (order_line.unit_price, order_line.line_total,
--  settlement.*) are documented in comments.
-- ============================================================
