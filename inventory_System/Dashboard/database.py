"""Production database access layer with connection pooling and retry."""
import asyncio
import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, date as date_type
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from Dashboard.config import config

logger = logging.getLogger("store.db")


class DatabasePool:
    _instance: Optional["DatabasePool"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pool = None
        return cls._instance

    async def initialize(self, max_retries: int = 10, delay: float = 2.0) -> None:
        if self._pool is not None:
            return
        for attempt in range(1, max_retries + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    host=config.POSTGRES_HOST,
                    port=config.POSTGRES_PORT,
                    database=config.POSTGRES_DB,
                    user=config.POSTGRES_USER,
                    password=config.POSTGRES_PASSWORD,
                    min_size=2, max_size=config.POSTGRES_POOL_SIZE,
                    command_timeout=60,
                    server_settings={'jit': 'off', 'application_name': 'store_inventory'}
                )
                logger.info("Database pool initialized")
                # Ensure required functions exist (for existing databases)
                await self._ensure_functions()
                return
            except Exception as e:
                logger.warning(f"DB connection attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(delay * attempt)
                else:
                    raise

    async def _ensure_functions(self) -> None:
        """Create the place_order_multi function if it doesn't exist (for existing DBs)."""
        sql = """
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
        """
        try:
            async with self.acquire() as conn:
                await conn.execute(sql)
            logger.info("Ensured place_order_multi function exists")
        except Exception as e:
            logger.error(f"Error creating place_order_multi function: {e}")
            raise

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

    @asynccontextmanager
    async def acquire(self):
        if self._pool is None:
            await self.initialize()
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self, isolation: str = "read_committed"):
        async with self.acquire() as conn:
            async with conn.transaction(isolation=isolation):
                yield conn

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def execute_many(self, query: str, args: List[Tuple]) -> None:
        async with self.acquire() as conn:
            await conn.executemany(query, args)


db = DatabasePool()


class InventoryQueries:
    @staticmethod
    async def get_inventory_status(
        search: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100, offset: int = 0
    ) -> Tuple[List[asyncpg.Record], int]:
        conditions = ["is_active = TRUE"]
        params: List[Any] = []
        if search:
            params.append(f"%{search}%")
            conditions.append(f"(product_name ILIKE ${len(params)} OR product_category ILIKE ${len(params)})")
        if category:
            params.append(category)
            conditions.append(f"product_category = ${len(params)}")
        if status:
            params.append(status)
            conditions.append(f"stock_status = ${len(params)}")
        where = " AND ".join(conditions)
        count_q = f"SELECT COUNT(*) FROM v_inventory_status WHERE {where}"
        data_q = f"SELECT * FROM v_inventory_status WHERE {where} ORDER BY product_name LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
        params.extend([limit, offset])
        total = await db.fetchval(count_q, *params[:-2]) or 0
        rows = await db.fetch(data_q, *params)
        return rows, total

    @staticmethod
    async def get_stock_summary() -> Optional[asyncpg.Record]:
        return await db.fetchrow("SELECT * FROM mv_inventory_summary")

    @staticmethod
    async def update_inventory(product_id: int, quantity: int, stock_price: float, threshold: int) -> None:
        await db.execute(
            "UPDATE inventory SET quantity=$1, stock_price=$2, low_stock_threshold=$3, updated_at=NOW() WHERE product_id=$4",
            quantity, stock_price, threshold, product_id
        )


class OrderQueries:
    @staticmethod
    async def get_orders_summary(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100, offset: int = 0
    ) -> Tuple[List[asyncpg.Record], int]:
        conditions = ["1=1"]
        params: List[Any] = []
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                start_date_obj = None
            if start_date_obj:
                params.append(start_date_obj)
                conditions.append(f"order_date >= ${len(params)}")
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                end_date_obj = None
            if end_date_obj:
                params.append(end_date_obj)
                conditions.append(f"order_date <= ${len(params)}")
        where = " AND ".join(conditions)
        count_q = f"SELECT COUNT(*) FROM v_order_summary WHERE {where}"
        data_q = f"SELECT * FROM v_order_summary WHERE {where} ORDER BY order_date DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
        params.extend([limit, offset])
        total = await db.fetchval(count_q, *params[:-2]) or 0
        rows = await db.fetch(data_q, *params)
        return rows, total

    @staticmethod
    async def get_total_orders() -> int:
        return await db.fetchval("SELECT COUNT(*) FROM orders WHERE status='Completed'") or 0

    @staticmethod
    async def get_total_sales() -> float:
        return await db.fetchval("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status='Completed'") or 0.0

    @staticmethod
    async def get_stock_value() -> float:
        return await db.fetchval("SELECT COALESCE(SUM(quantity*stock_price),0) FROM inventory") or 0.0

    @staticmethod
    async def place_order_safe(product_id: int, quantity: int, unit_price: float, order_date, notes: Optional[str] = None) -> Tuple[int, str]:
        row = await db.fetchrow("SELECT * FROM place_order($1,$2,$3,$4,$5)", product_id, quantity, unit_price, order_date, notes)
        return row["order_id"], row["order_number"]

    @staticmethod
    async def place_order_multi(items: List[Dict], order_date, notes: Optional[str] = None) -> Tuple[int, str]:
        """items: list of {'product_id': int, 'quantity': int, 'unit_price': float}"""
        json_items = json.dumps(items)
        row = await db.fetchrow(
            "SELECT * FROM place_order_multi($1::jsonb, $2, $3)",
            json_items, order_date, notes
        )
        return row["order_id"], row["order_number"]

    @staticmethod
    async def get_order_by_id(order_id: int) -> Optional[asyncpg.Record]:
        return await db.fetchrow(
            """SELECT o.*, jsonb_agg(jsonb_build_object('product_name',oi.product_name,'product_category',oi.product_category,'quantity',oi.quantity,'unit_price',oi.unit_price,'total_price',oi.total_price)) as items
               FROM orders o LEFT JOIN order_items oi ON o.order_id=oi.order_id WHERE o.order_id=$1 GROUP BY o.order_id""",
            order_id
        )

    @staticmethod
    async def cancel_order(order_id: int) -> None:
        async with db.transaction(isolation="serializable") as conn:
            items = await conn.fetch("SELECT product_id, quantity FROM order_items WHERE order_id=$1", order_id)
            for item in items:
                await conn.execute("UPDATE inventory SET quantity=quantity+$1 WHERE product_id=$2", item["quantity"], item["product_id"])
                prev = await conn.fetchval("SELECT quantity FROM inventory WHERE product_id=$1", item["product_id"])
                await conn.execute(
                    "INSERT INTO stock_transactions (product_id,transaction_type,quantity_change,previous_qty,new_qty,reference_id,notes) VALUES ($1,'Return',$2,$3,$4,$5,'Order cancellation')",
                    item["product_id"], item["quantity"], prev - item["quantity"], prev, order_id
                )
            await conn.execute("UPDATE orders SET status='Cancelled', updated_at=NOW() WHERE order_id=$1", order_id)


class ProductQueries:
    @staticmethod
    async def get_products(search: Optional[str] = None, category_id: Optional[int] = None, active_only: bool = True, limit: int = 100, offset: int = 0) -> Tuple[List[asyncpg.Record], int]:
        conditions = []
        params: List[Any] = []
        if active_only:
            conditions.append("p.is_active = TRUE")
        if search:
            params.append(f"%{search}%")
            conditions.append(f"(p.product_name ILIKE ${len(params)} OR c.category_name ILIKE ${len(params)})")
        if category_id:
            params.append(category_id)
            conditions.append(f"p.category_id = ${len(params)}")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        count_q = f"SELECT COUNT(*) FROM products p JOIN categories c ON p.category_id=c.category_id{where}"
        data_q = f"""
            SELECT p.*, c.category_name, i.quantity, i.stock_price, i.stock_status
            FROM products p
            JOIN categories c ON p.category_id=c.category_id
            LEFT JOIN inventory i ON p.product_id=i.product_id
            {where}
            ORDER BY p.product_name
            LIMIT ${len(params)+1} OFFSET ${len(params)+2}
        """
        params.extend([limit, offset])
        total = await db.fetchval(count_q, *params[:-2]) or 0
        rows = await db.fetch(data_q, *params)
        return rows, total

    @staticmethod
    async def get_product_by_id(product_id: int) -> Optional[asyncpg.Record]:
        return await db.fetchrow(
            "SELECT p.*, c.category_name, i.quantity, i.stock_price, i.stock_status, i.low_stock_threshold FROM products p JOIN categories c ON p.category_id=c.category_id LEFT JOIN inventory i ON p.product_id=i.product_id WHERE p.product_id=$1",
            product_id
        )

    @staticmethod
    async def create_product(name: str, category_id: int, price: float, quantity: int = 0, stock_price: float = 0) -> int:
        async with db.transaction() as conn:
            pid = await conn.fetchval("INSERT INTO products (product_name,category_id,product_price) VALUES ($1,$2,$3) RETURNING product_id", name, category_id, price)
            await conn.execute("INSERT INTO inventory (product_id,quantity,stock_price,low_stock_threshold) VALUES ($1,$2,$3,$4)", pid, quantity, stock_price, config.LOW_STOCK_THRESHOLD)
            return pid

    @staticmethod
    async def update_product(product_id: int, name: str, category_id: int, price: float) -> None:
        await db.execute("UPDATE products SET product_name=$1, category_id=$2, product_price=$3 WHERE product_id=$4", name, category_id, price, product_id)

    @staticmethod
    async def soft_delete_product(product_id: int) -> None:
        await db.execute("UPDATE products SET is_active=FALSE, updated_at=NOW() WHERE product_id=$1", product_id)


class SupplierQueries:
    @staticmethod
    async def get_suppliers(search: Optional[str] = None, category: Optional[str] = None, limit: int = 100, offset: int = 0) -> Tuple[List[asyncpg.Record], int]:
        conditions = ["is_active = TRUE"]
        params: List[Any] = []
        if search:
            params.append(f"%{search}%")
            conditions.append(f"(supplier_name ILIKE ${len(params)} OR supplier_number ILIKE ${len(params)})")
        if category:
            params.append(category)
            conditions.append(f"product_category = ${len(params)}")
        where = " AND ".join(conditions)
        count_q = f"SELECT COUNT(*) FROM v_supplier_inventory WHERE {where}"
        data_q = f"SELECT * FROM v_supplier_inventory WHERE {where} ORDER BY supplier_name LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
        params.extend([limit, offset])
        total = await db.fetchval(count_q, *params[:-2]) or 0
        rows = await db.fetch(data_q, *params)
        return rows, total


class AnalyticsQueries:
    @staticmethod
    async def get_sales_trend(days: int = 30) -> List[asyncpg.Record]:
        return await db.fetch("SELECT order_date, total_orders, total_orders_price FROM v_order_summary WHERE order_date >= CURRENT_DATE - $1::INTEGER ORDER BY order_date", days)

    @staticmethod
    async def get_product_performance(limit: int = 10) -> List[asyncpg.Record]:
        return await db.fetch("SELECT * FROM mv_product_sales_performance ORDER BY revenue DESC LIMIT $1", limit)

    @staticmethod
    async def get_category_performance() -> List[asyncpg.Record]:
        return await db.fetch("SELECT * FROM mv_category_performance ORDER BY revenue DESC")

    @staticmethod
    async def get_stock_distribution() -> List[asyncpg.Record]:
        return await db.fetch("SELECT stock_status, COUNT(*) as count, SUM(quantity) as total_qty FROM inventory i JOIN products p ON i.product_id=p.product_id WHERE p.is_active=TRUE GROUP BY stock_status")

    @staticmethod
    async def refresh_materialized_views() -> None:
        sql = """
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
        """
        await db.execute(sql)
        logger.info("Materialized views refreshed via direct SQL")


class AdminQueries:
    @staticmethod
    async def get_table_names() -> List[str]:
        rows = await db.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
        return [r["table_name"] for r in rows]

    @staticmethod
    async def get_table_columns(table_name: str) -> List[asyncpg.Record]:
        return await db.fetch("SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position", table_name)

    @staticmethod
    async def get_table_data(table_name: str, limit: int = 100, offset: int = 0) -> Tuple[List[asyncpg.Record], int]:
        allowed = await AdminQueries.get_table_names()
        if table_name not in allowed:
            raise ValueError(f"Table {table_name} not found")
        count = await db.fetchval(f"SELECT COUNT(*) FROM {table_name}")
        rows = await db.fetch(f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT $1 OFFSET $2", limit, offset)
        return rows, count

    @staticmethod
    async def get_categories() -> List[asyncpg.Record]:
        return await db.fetch("SELECT * FROM categories ORDER BY category_name")

    @staticmethod
    async def get_total_record_count() -> int:
        result = await db.fetchrow("""SELECT (SELECT COUNT(*) FROM products WHERE is_active=TRUE) + (SELECT COUNT(*) FROM orders) + (SELECT COUNT(*) FROM suppliers WHERE is_active=TRUE) + (SELECT COUNT(*) FROM inventory) as total""")
        return result["total"] or 0