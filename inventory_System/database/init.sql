-- =====================================================
-- Production-Grade Store Inventory & Order Management
-- Database Schema (PostgreSQL 16+)
-- =====================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- Lookup Tables
-- =====================================================

CREATE TABLE IF NOT EXISTS categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    description   TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Core Entities
-- =====================================================

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    product_name    VARCHAR(255) NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    product_price   NUMERIC(12,2) NOT NULL CHECK (product_price >= 0),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_product_name_category UNIQUE (product_name, category_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id    SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL UNIQUE REFERENCES products(product_id) ON DELETE CASCADE,
    quantity        INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    stock_price     NUMERIC(12,2) NOT NULL DEFAULT 0.00 CHECK (stock_price >= 0),
    low_stock_threshold INTEGER NOT NULL DEFAULT 10 CHECK (low_stock_threshold >= 0),
    stock_status    VARCHAR(20) NOT NULL DEFAULT 'In Stock',
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_stock_status CHECK (stock_status IN ('In Stock', 'Low Stock', 'Out of Stock'))
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     SERIAL PRIMARY KEY,
    supplier_name   VARCHAR(255) NOT NULL,
    supplier_number VARCHAR(50) NOT NULL UNIQUE,
    category_id     INTEGER REFERENCES categories(category_id) ON DELETE SET NULL,
    contact_info    JSONB,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS supplier_products (
    supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    supply_price NUMERIC(12,2),
    lead_time_days INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (supplier_id, product_id)
);

-- =====================================================
-- Orders (Normalized: header + lines)
-- =====================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    order_number    VARCHAR(50) NOT NULL UNIQUE,
    order_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    total_amount    NUMERIC(12,2) NOT NULL DEFAULT 0.00 CHECK (total_amount >= 0),
    status          VARCHAR(20) NOT NULL DEFAULT 'Completed' CHECK (status IN ('Completed', 'Cancelled', 'Pending')),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    product_name    VARCHAR(255) NOT NULL,
    product_category VARCHAR(100) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    total_price     NUMERIC(12,2) NOT NULL CHECK (total_price >= 0),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Audit & Transactions
-- =====================================================

CREATE TABLE IF NOT EXISTS stock_transactions (
    transaction_id  SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('Sale', 'Purchase', 'Adjustment', 'Return')),
    quantity_change INTEGER NOT NULL,
    previous_qty    INTEGER NOT NULL,
    new_qty         INTEGER NOT NULL,
    reference_id    INTEGER,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id        SERIAL PRIMARY KEY,
    table_name      VARCHAR(50) NOT NULL,
    record_id       INTEGER NOT NULL,
    action          VARCHAR(20) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_values      JSONB,
    new_values      JSONB,
    performed_at    TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Indexes
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_products_created ON products(created_at);

CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_status ON inventory(stock_status);
CREATE INDEX IF NOT EXISTS idx_inventory_low_stock ON inventory(stock_status) WHERE stock_status = 'Low Stock';

CREATE INDEX IF NOT EXISTS idx_orders_number ON orders(order_number);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date_status ON orders(order_date, status);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);

CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(supplier_name);
CREATE INDEX IF NOT EXISTS idx_suppliers_category ON suppliers(category_id);
CREATE INDEX IF NOT EXISTS idx_suppliers_active ON suppliers(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_stock_tx_product ON stock_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_tx_created ON stock_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_table_record ON audit_log(table_name, record_id);

-- =====================================================
-- Functions & Triggers
-- =====================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_updated ON products;
CREATE TRIGGER trg_products_updated
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_inventory_updated ON inventory;
CREATE TRIGGER trg_inventory_updated
    BEFORE UPDATE ON inventory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_suppliers_updated ON suppliers;
CREATE TRIGGER trg_suppliers_updated
    BEFORE UPDATE ON suppliers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_orders_updated ON orders;
CREATE TRIGGER trg_orders_updated
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE FUNCTION calculate_stock_status()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.quantity <= 0 THEN
        NEW.stock_status := 'Out of Stock';
    ELSIF NEW.quantity <= NEW.low_stock_threshold THEN
        NEW.stock_status := 'Low Stock';
    ELSE
        NEW.stock_status := 'In Stock';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inventory_stock_status ON inventory;
CREATE TRIGGER trg_inventory_stock_status
    BEFORE INSERT OR UPDATE ON inventory
    FOR EACH ROW EXECUTE FUNCTION calculate_stock_status();

CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_values)
        VALUES (TG_TABLE_NAME, OLD.product_id, 'DELETE', row_to_json(OLD));
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values)
        VALUES (TG_TABLE_NAME, NEW.product_id, 'UPDATE', row_to_json(OLD), row_to_json(NEW));
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log (table_name, record_id, action, new_values)
        VALUES (TG_TABLE_NAME, NEW.product_id, 'INSERT', row_to_json(NEW));
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_audit ON products;
CREATE TRIGGER trg_products_audit
    AFTER INSERT OR UPDATE OR DELETE ON products
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();

CREATE OR REPLACE FUNCTION update_order_total()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE orders
    SET total_amount = (
        SELECT COALESCE(SUM(total_price), 0)
        FROM order_items
        WHERE order_id = COALESCE(NEW.order_id, OLD.order_id)
    ),
    updated_at = NOW()
    WHERE order_id = COALESCE(NEW.order_id, OLD.order_id);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION place_order_multi(
    p_items JSONB,
    p_order_date DATE DEFAULT CURRENT_DATE,
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE(order_id INTEGER, order_number VARCHAR) AS $$
DECLARE
    v_order_id INTEGER;
    v_order_number VARCHAR(50);
    v_item RECORD;
    v_available INTEGER;
    v_product_name VARCHAR(255);
    v_category_name VARCHAR(100);
BEGIN
    v_order_number := 'ORD-' || TO_CHAR(p_order_date, 'YYYYMMDD') || '-' || LPAD(NEXTVAL('orders_order_id_seq')::TEXT, 6, '0');

    INSERT INTO orders (order_number, order_date, status, notes)
    VALUES (v_order_number, p_order_date, 'Completed', p_notes)
    RETURNING orders.order_id INTO v_order_id;

    FOR v_item IN SELECT * FROM jsonb_to_recordset(p_items) AS x(product_id INTEGER, quantity INTEGER, unit_price NUMERIC)
    LOOP
        SELECT i.quantity, p.product_name, c.category_name
        INTO v_available, v_product_name, v_category_name
        FROM inventory i
        JOIN products p ON i.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE i.product_id = v_item.product_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Product % not found', v_item.product_id;
        END IF;
        IF v_available < v_item.quantity THEN
            RAISE EXCEPTION 'Insufficient stock for product % (available %)', v_item.product_id, v_available;
        END IF;

        INSERT INTO order_items (order_id, product_id, product_name, product_category, quantity, unit_price, total_price)
        VALUES (v_order_id, v_item.product_id, v_product_name, v_category_name, v_item.quantity, v_item.unit_price, v_item.quantity * v_item.unit_price);

        UPDATE inventory SET quantity = quantity - v_item.quantity, updated_at = NOW() WHERE product_id = v_item.product_id;

        INSERT INTO stock_transactions (product_id, transaction_type, quantity_change, previous_qty, new_qty, reference_id, notes)
        VALUES (v_item.product_id, 'Sale', -v_item.quantity, v_available, v_available - v_item.quantity, v_order_id, 'Order ' || v_order_number);
    END LOOP;

    RETURN QUERY SELECT v_order_id, v_order_number;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- refresh_analytics() – Drops and recreates materialized views
-- =====================================================

CREATE OR REPLACE FUNCTION refresh_analytics()
RETURNS VOID AS $$
BEGIN
    DROP MATERIALIZED VIEW IF EXISTS mv_daily_sales CASCADE;
    CREATE MATERIALIZED VIEW mv_daily_sales AS
    SELECT 
        order_date,
        COUNT(DISTINCT order_id) AS total_orders,
        COALESCE(SUM(total_amount), 0) AS total_revenue,
        AVG(total_amount) AS avg_order_value
    FROM orders
    WHERE status = 'Completed'
    GROUP BY order_date
    ORDER BY order_date DESC;
    CREATE UNIQUE INDEX idx_mv_daily_sales_date ON mv_daily_sales(order_date);

    DROP MATERIALIZED VIEW IF EXISTS mv_monthly_sales CASCADE;
    CREATE MATERIALIZED VIEW mv_monthly_sales AS
    SELECT 
        DATE_TRUNC('month', order_date) AS month,
        COUNT(DISTINCT order_id) AS total_orders,
        COALESCE(SUM(total_amount), 0) AS total_revenue,
        AVG(total_amount) AS avg_order_value
    FROM orders
    WHERE status = 'Completed'
    GROUP BY DATE_TRUNC('month', order_date)
    ORDER BY month DESC;
    CREATE UNIQUE INDEX idx_mv_monthly_sales_month ON mv_monthly_sales(month);

    DROP MATERIALIZED VIEW IF EXISTS mv_product_sales_performance CASCADE;
    CREATE MATERIALIZED VIEW mv_product_sales_performance AS
    SELECT 
        p.product_id, p.product_name, c.category_name,
        COALESCE(SUM(oi.quantity), 0) AS units_sold,
        COALESCE(SUM(oi.total_price), 0) AS revenue,
        COUNT(DISTINCT oi.order_id) AS order_count
    FROM products p
    JOIN categories c ON p.category_id = c.category_id
    LEFT JOIN order_items oi ON p.product_id = oi.product_id
    LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'Completed'
    WHERE p.is_active = TRUE
    GROUP BY p.product_id, p.product_name, c.category_name;
    CREATE UNIQUE INDEX idx_mv_product_perf_id ON mv_product_sales_performance(product_id);

    DROP MATERIALIZED VIEW IF EXISTS mv_category_performance CASCADE;
    CREATE MATERIALIZED VIEW mv_category_performance AS
    SELECT 
        c.category_id, c.category_name,
        COUNT(DISTINCT oi.order_id) AS order_count,
        COALESCE(SUM(oi.quantity), 0) AS units_sold,
        COALESCE(SUM(oi.total_price), 0) AS revenue
    FROM categories c
    LEFT JOIN products p ON c.category_id = p.category_id AND p.is_active = TRUE
    LEFT JOIN order_items oi ON p.product_id = oi.product_id
    LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'Completed'
    GROUP BY c.category_id, c.category_name;
    CREATE UNIQUE INDEX idx_mv_category_perf_id ON mv_category_performance(category_id);

    DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE;
    CREATE MATERIALIZED VIEW mv_inventory_summary AS
    SELECT 
        COUNT(*) AS total_products,
        SUM(CASE WHEN stock_status = 'In Stock' THEN 1 ELSE 0 END) AS in_stock_count,
        SUM(CASE WHEN stock_status = 'Low Stock' THEN 1 ELSE 0 END) AS low_stock_count,
        SUM(CASE WHEN stock_status = 'Out of Stock' THEN 1 ELSE 0 END) AS out_of_stock_count,
        COALESCE(SUM(quantity * stock_price), 0) AS total_stock_value
    FROM v_inventory_status;
    CREATE UNIQUE INDEX idx_mv_inventory_summary ON mv_inventory_summary((1));
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Views
-- =====================================================

CREATE OR REPLACE VIEW v_inventory_status AS
SELECT 
    p.product_id,
    p.product_name,
    c.category_name AS product_category,
    i.quantity,
    i.stock_price,
    p.product_price,
    i.stock_status,
    i.low_stock_threshold,
    i.updated_at,
    p.is_active
FROM products p
JOIN categories c ON p.category_id = c.category_id
JOIN inventory i ON p.product_id = i.product_id
WHERE p.is_active = TRUE;

CREATE OR REPLACE VIEW v_order_summary AS
SELECT 
    o.order_date,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COALESCE(SUM(o.total_amount), 0) AS total_orders_price
FROM orders o
WHERE o.status = 'Completed'
GROUP BY o.order_date
ORDER BY o.order_date DESC;

CREATE OR REPLACE VIEW v_supplier_inventory AS
SELECT 
    s.supplier_id,
    s.supplier_name,
    c.category_name AS product_category,
    COALESCE(i.stock_status, 'N/A') AS stock_status,
    COALESCE(i.quantity, 0) AS stock_quantity,
    s.supplier_number,
    s.is_active
FROM suppliers s
LEFT JOIN categories c ON s.category_id = c.category_id
LEFT JOIN supplier_products sp ON s.supplier_id = sp.supplier_id
LEFT JOIN inventory i ON sp.product_id = i.product_id
WHERE s.is_active = TRUE;

CREATE OR REPLACE VIEW v_product_performance AS
SELECT 
    p.product_id,
    p.product_name AS product,
    c.category_name AS category,
    COUNT(DISTINCT oi.order_id) AS orders_count,
    COALESCE(SUM(oi.quantity), 0) AS units_sold,
    COALESCE(SUM(oi.total_price), 0) AS revenue,
    COALESCE(i.quantity, 0) AS current_stock,
    i.stock_status
FROM products p
JOIN categories c ON p.category_id = c.category_id
LEFT JOIN inventory i ON p.product_id = i.product_id
LEFT JOIN order_items oi ON p.product_id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'Completed'
WHERE p.is_active = TRUE
GROUP BY p.product_id, p.product_name, c.category_name, i.quantity, i.stock_status;

-- =====================================================
-- Materialized Views (initial creation)
-- =====================================================

DROP MATERIALIZED VIEW IF EXISTS mv_daily_sales CASCADE;
CREATE MATERIALIZED VIEW mv_daily_sales AS
SELECT 
    order_date,
    COUNT(DISTINCT order_id) AS total_orders,
    COALESCE(SUM(total_amount), 0) AS total_revenue,
    AVG(total_amount) AS avg_order_value
FROM orders
WHERE status = 'Completed'
GROUP BY order_date
ORDER BY order_date DESC;

CREATE UNIQUE INDEX idx_mv_daily_sales_date ON mv_daily_sales(order_date);

DROP MATERIALIZED VIEW IF EXISTS mv_monthly_sales CASCADE;
CREATE MATERIALIZED VIEW mv_monthly_sales AS
SELECT 
    DATE_TRUNC('month', order_date) AS month,
    COUNT(DISTINCT order_id) AS total_orders,
    COALESCE(SUM(total_amount), 0) AS total_revenue,
    AVG(total_amount) AS avg_order_value
FROM orders
WHERE status = 'Completed'
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month DESC;

CREATE UNIQUE INDEX idx_mv_monthly_sales_month ON mv_monthly_sales(month);

DROP MATERIALIZED VIEW IF EXISTS mv_product_sales_performance CASCADE;
CREATE MATERIALIZED VIEW mv_product_sales_performance AS
SELECT 
    p.product_id,
    p.product_name,
    c.category_name,
    COALESCE(SUM(oi.quantity), 0) AS units_sold,
    COALESCE(SUM(oi.total_price), 0) AS revenue,
    COUNT(DISTINCT oi.order_id) AS order_count
FROM products p
JOIN categories c ON p.category_id = c.category_id
LEFT JOIN order_items oi ON p.product_id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'Completed'
WHERE p.is_active = TRUE
GROUP BY p.product_id, p.product_name, c.category_name;

CREATE UNIQUE INDEX idx_mv_product_perf_id ON mv_product_sales_performance(product_id);

DROP MATERIALIZED VIEW IF EXISTS mv_category_performance CASCADE;
CREATE MATERIALIZED VIEW mv_category_performance AS
SELECT 
    c.category_id,
    c.category_name,
    COUNT(DISTINCT oi.order_id) AS order_count,
    COALESCE(SUM(oi.quantity), 0) AS units_sold,
    COALESCE(SUM(oi.total_price), 0) AS revenue
FROM categories c
LEFT JOIN products p ON c.category_id = p.category_id AND p.is_active = TRUE
LEFT JOIN order_items oi ON p.product_id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status = 'Completed'
GROUP BY c.category_id, c.category_name;

CREATE UNIQUE INDEX idx_mv_category_perf_id ON mv_category_performance(category_id);

DROP MATERIALIZED VIEW IF EXISTS mv_inventory_summary CASCADE;
CREATE MATERIALIZED VIEW mv_inventory_summary AS
SELECT 
    COUNT(*) AS total_products,
    SUM(CASE WHEN stock_status = 'In Stock' THEN 1 ELSE 0 END) AS in_stock_count,
    SUM(CASE WHEN stock_status = 'Low Stock' THEN 1 ELSE 0 END) AS low_stock_count,
    SUM(CASE WHEN stock_status = 'Out of Stock' THEN 1 ELSE 0 END) AS out_of_stock_count,
    COALESCE(SUM(quantity * stock_price), 0) AS total_stock_value
FROM v_inventory_status;

CREATE UNIQUE INDEX idx_mv_inventory_summary ON mv_inventory_summary((1));

-- =====================================================
-- Application Functions
-- =====================================================

CREATE OR REPLACE FUNCTION place_order(
    p_product_id INTEGER,
    p_quantity INTEGER,
    p_unit_price NUMERIC,
    p_order_date DATE DEFAULT CURRENT_DATE,
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE(order_id INTEGER, order_number VARCHAR) AS $$
DECLARE
    v_order_id INTEGER;
    v_order_number VARCHAR(50);
    v_available INTEGER;
    v_product_name VARCHAR(255);
    v_category_name VARCHAR(100);
    v_current_price NUMERIC(12,2);
BEGIN
    SELECT i.quantity, p.product_name, c.category_name, p.product_price
    INTO v_available, v_product_name, v_category_name, v_current_price
    FROM inventory i
    JOIN products p ON i.product_id = p.product_id
    JOIN categories c ON p.category_id = c.category_id
    WHERE i.product_id = p_product_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found in inventory';
    END IF;

    IF v_available < p_quantity THEN
        RAISE EXCEPTION 'Insufficient stock. Available: %, Requested: %', v_available, p_quantity;
    END IF;

    v_order_number := 'ORD-' || TO_CHAR(p_order_date, 'YYYYMMDD') || '-' || LPAD(NEXTVAL('orders_order_id_seq')::TEXT, 6, '0');

    INSERT INTO orders (order_number, order_date, status, notes)
    VALUES (v_order_number, p_order_date, 'Completed', p_notes)
    RETURNING orders.order_id INTO v_order_id;

    INSERT INTO order_items (order_id, product_id, product_name, product_category, quantity, unit_price, total_price)
    VALUES (v_order_id, p_product_id, v_product_name, v_category_name, p_quantity, p_unit_price, p_quantity * p_unit_price);

    UPDATE inventory
    SET quantity = quantity - p_quantity, updated_at = NOW()
    WHERE product_id = p_product_id;

    INSERT INTO stock_transactions (product_id, transaction_type, quantity_change, previous_qty, new_qty, reference_id, notes)
    VALUES (p_product_id, 'Sale', -p_quantity, v_available, v_available - p_quantity, v_order_id, 'Order ' || v_order_number);

    RETURN QUERY SELECT v_order_id, v_order_number;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Seed Data
-- =====================================================

INSERT INTO categories (category_name, description) VALUES
    ('Groceries', 'Daily grocery items'),
    ('Beverages', 'Drinks and beverages'),
    ('Household', 'Household supplies'),
    ('Personal Care', 'Personal hygiene products'),
    ('Snacks', 'Snacks and confectionery')
ON CONFLICT (category_name) DO NOTHING;

INSERT INTO products (product_name, category_id, product_price) VALUES
    ('Rice Basmati 5kg', 1, 850.00),
    ('Wheat Flour 10kg', 1, 650.00),
    ('Cooking Oil 5L', 1, 1200.00),
    ('Sugar 1kg', 1, 120.00),
    ('Tea Premium 500g', 2, 450.00),
    ('Soft Drink 1.5L', 2, 95.00),
    ('Mineral Water 6x1.5L', 2, 180.00),
    ('Dishwashing Liquid', 3, 220.00),
    ('Laundry Detergent 2kg', 3, 550.00),
    ('Toothpaste 150g', 4, 180.00),
    ('Shampoo 400ml', 4, 350.00),
    ('Soap Bar', 4, 85.00),
    ('Potato Chips', 5, 60.00),
    ('Biscuits Premium', 5, 120.00),
    ('Chocolate Bar', 5, 150.00)
ON CONFLICT DO NOTHING;

INSERT INTO inventory (product_id, quantity, stock_price, low_stock_threshold) VALUES
    (1, 120, 750.00, 20),
    (2, 85, 580.00, 15),
    (3, 45, 1050.00, 10),
    (4, 200, 95.00, 50),
    (5, 60, 380.00, 12),
    (6, 150, 75.00, 30),
    (7, 80, 150.00, 15),
    (8, 40, 180.00, 10),
    (9, 55, 480.00, 12),
    (10, 100, 150.00, 25),
    (11, 70, 290.00, 15),
    (12, 180, 65.00, 40),
    (13, 90, 45.00, 20),
    (14, 110, 95.00, 25),
    (15, 75, 120.00, 15)
ON CONFLICT (product_id) DO NOTHING;

INSERT INTO suppliers (supplier_name, supplier_number, category_id, contact_info) VALUES
    ('Pakistan Foods Ltd', 'SUP-001', 1, '{"phone": "+92-300-1234567", "email": "info@pakfoods.com"}'),
    ('Refresh Beverages', 'SUP-002', 2, '{"phone": "+92-301-7654321", "email": "orders@refreshbev.com"}'),
    ('CleanHome Supplies', 'SUP-003', 3, '{"phone": "+92-302-9876543", "email": "sales@cleanhome.pk"}'),
    ('Personal Care Co', 'SUP-004', 4, '{"phone": "+92-303-4567890", "email": "contact@pcare.com"}'),
    ('Snack Masters', 'SUP-005', 5, '{"phone": "+92-304-1122334", "email": "orders@snackmasters.pk"}')
ON CONFLICT (supplier_number) DO NOTHING;

INSERT INTO supplier_products (supplier_id, product_id, supply_price, lead_time_days) VALUES
    (1, 1, 720.00, 3), (1, 2, 550.00, 2), (1, 3, 980.00, 5), (1, 4, 88.00, 2),
    (2, 5, 380.00, 4), (2, 6, 72.00, 2), (2, 7, 140.00, 3),
    (3, 8, 165.00, 3), (3, 9, 440.00, 4),
    (4, 10, 140.00, 5), (4, 11, 270.00, 3), (4, 12, 58.00, 2),
    (5, 13, 38.00, 2), (5, 14, 88.00, 3), (5, 15, 105.00, 4)
ON CONFLICT DO NOTHING;

-- Seed historical orders
DO $$
DECLARE
    i INTEGER;
    v_date DATE;
    v_product_id INTEGER;
    v_qty INTEGER;
    v_price NUMERIC;
    v_order_id INTEGER;
    v_order_num VARCHAR;
    v_prod_name VARCHAR;
    v_cat_name VARCHAR;
    v_avail INTEGER;
BEGIN
    FOR i IN 1..50 LOOP
        v_date := CURRENT_DATE - (random() * 60)::INTEGER;
        SELECT product_id, product_name, product_category, product_price, quantity
        INTO v_product_id, v_prod_name, v_cat_name, v_price, v_avail
        FROM v_inventory_status
        ORDER BY random()
        LIMIT 1;

        v_qty := 1 + (random() * LEAST(5, GREATEST(0, v_avail - 1)))::INTEGER;

        IF v_qty > 0 AND v_avail >= v_qty THEN
            v_order_num := 'ORD-' || TO_CHAR(v_date, 'YYYYMMDD') || '-' || LPAD((1000 + i)::TEXT, 6, '0');

            INSERT INTO orders (order_number, order_date, status, notes)
            VALUES (v_order_num, v_date, 'Completed', 'Auto-generated seed order')
            RETURNING order_id INTO v_order_id;

            INSERT INTO order_items (order_id, product_id, product_name, product_category, quantity, unit_price, total_price)
            VALUES (v_order_id, v_product_id, v_prod_name, v_cat_name, v_qty, v_price, v_qty * v_price);

            UPDATE inventory SET quantity = quantity - v_qty WHERE product_id = v_product_id;

            INSERT INTO stock_transactions (product_id, transaction_type, quantity_change, previous_qty, new_qty, reference_id, notes)
            VALUES (v_product_id, 'Sale', -v_qty, v_avail, v_avail - v_qty, v_order_id, 'Seed order ' || v_order_num);
        END IF;
    END LOOP;
END $$;

-- Initial refresh
SELECT refresh_analytics();