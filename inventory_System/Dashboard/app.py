"""
Production-Grade Store Inventory & Order Management System
Dashboard Application (NiceGUI + Plotly + PostgreSQL)
"""
import asyncio
import json
from datetime import datetime, date as date_type
from typing import Any, Dict, List, Optional, Callable

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from nicegui import ui, app

from Dashboard.config import config
from Dashboard.database import db, InventoryQueries, OrderQueries, ProductQueries, SupplierQueries, AnalyticsQueries, AdminQueries
from Dashboard.i18n import i18n
from Dashboard.utils import (
    format_currency, format_number, format_date, format_date_short,
    get_current_month_range, get_theme_colors, logger
)

# =========================================================
# Global Application State
# =========================================================

class AppState:
    def __init__(self):
        self.theme: str = "light"
        self.lang: str = "en"
        self.last_updated: datetime = datetime.now()
        self.total_records: int = 0
        self.date_start: str = ""
        self.date_end: str = ""
        self.current_admin_table: str = "products"
        self.lbl_total: Optional[ui.label] = None
        self.lbl_updated: Optional[ui.label] = None
        self.kpi_orders: Optional[ui.label] = None
        self.kpi_sales: Optional[ui.label] = None
        self.kpi_stock: Optional[ui.label] = None
        self.inv_search: Optional[ui.input] = None
        self.inv_table: Optional[ui.table] = None
        self.order_table: Optional[ui.table] = None
        self.sup_search: Optional[ui.input] = None
        self.sup_table: Optional[ui.table] = None
        self.chart_sales: Optional[ui.plotly] = None
        self.chart_orders: Optional[ui.plotly] = None
        self.chart_products: Optional[ui.plotly] = None
        self.chart_stock: Optional[ui.plotly] = None
        self.chart_categories: Optional[ui.plotly] = None
        self.chart_dual: Optional[ui.plotly] = None
        self.db_admin_container: Optional[ui.element] = None
        self.dark_mode_obj = ui.dark_mode()
        self._refresh_callbacks: List[Callable] = []

    def set_language(self, lang: str) -> None:
        self.lang = lang
        i18n.set_language(lang)

    def register_refresh(self, callback: Callable) -> None:
        self._refresh_callbacks.append(callback)

    async def refresh_all(self) -> None:
        self.last_updated = datetime.now()
        for cb in self._refresh_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb()
                else:
                    result = cb()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as e:
                logger.error(f"Refresh callback error: {e}")

# =========================================================
# Theme & Styling
# =========================================================

def apply_theme(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    if state.theme == "dark":
        state.dark_mode_obj.enable()
    else:
        state.dark_mode_obj.disable()
    css = """
    :root {{
        --store-bg: {bg};
        --store-card: {card};
        --store-text: {text};
        --store-text-secondary: {text_secondary};
        --store-border: {border};
        --store-primary: {primary};
        --store-success: {success};
        --store-warning: {warning};
        --store-danger: {danger};
        --store-radius: 18px;
        --store-shadow: 0 12px 30px rgba(15, 23, 42, 0.07);
    }}

    * {{ box-sizing: border-box; }}
    html, body {{ min-height: 100%; }}
    body {{
        background:
            radial-gradient(circle at 10% 0%, rgba(99, 102, 241, 0.08), transparent 28%),
            radial-gradient(circle at 90% 10%, rgba(14, 165, 233, 0.07), transparent 30%),
            {bg} !important;
        color: {text} !important;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    .store-shell {{ width: min(1500px, calc(100% - 28px)); margin: 0 auto; }}
    .glass-card {{
        background: {card}ee !important;
        border: 1px solid {border} !important;
        border-radius: var(--store-radius) !important;
        box-shadow: var(--store-shadow);
        backdrop-filter: blur(12px);
    }}
    .section-card {{
        background: {card} !important;
        border: 1px solid {border} !important;
        border-radius: 18px !important;
        overflow: hidden;
        box-shadow: var(--store-shadow);
    }}
    .soft-panel {{
        background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0));
        border: 1px solid {border};
        border-radius: 14px;
    }}
    .kpi-card {{
        position: relative;
        min-height: 148px;
        overflow: hidden;
        transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
    }}
    .kpi-card:hover {{
        transform: translateY(-4px);
        box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
    }}
    .kpi-card::after {{
        content: "";
        position: absolute;
        width: 120px; height: 120px;
        right: -42px; top: -42px;
        border-radius: 999px;
        background: rgba(99,102,241,.08);
    }}
    .kpi-icon {{
        width: 52px; height: 52px;
        border-radius: 15px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
    }}
    .page-title {{ letter-spacing: -0.025em; }}
    .muted {{ color: {text_secondary} !important; }}
    .section-title {{ font-weight: 800; letter-spacing: -0.02em; }}
    .section-subtitle {{ color: {text_secondary}; font-size: .82rem; }}
    .status-pill {{
        border: 1px solid {border};
        border-radius: 999px;
        padding: 6px 11px;
        background: {bg}aa;
        font-size: 12px;
    }}

    .q-header {{
        box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08) !important;
        border-bottom: 1px solid {border} !important;
        backdrop-filter: blur(14px);
    }}
    .q-tabs {{
        border-radius: 14px;
        padding: 4px;
        background: {card};
        border: 1px solid {border};
        box-shadow: 0 8px 24px rgba(15, 23, 42, .06);
    }}
    .q-tab {{
        border-radius: 11px;
        min-height: 42px;
        font-weight: 700;
    }}
    .q-table__container {{
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid {border};
        box-shadow: none;
    }}
    .q-table thead tr {{
        background: rgba(99,102,241,.045);
    }}
    .q-table th {{
        font-weight: 800 !important;
        color: {text} !important;
        white-space: nowrap;
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .045em;
    }}
    .q-table td {{
        border-color: {border} !important;
        font-size: .86rem;
    }}
    .q-table tbody tr {{
        transition: background .15s ease, transform .15s ease;
    }}
    .q-table tbody tr:hover {{
        background: rgba(99,102,241,.035);
    }}
    .q-field--outlined .q-field__control {{
        border-radius: 12px;
    }}
    .q-btn {{
        border-radius: 11px;
        font-weight: 700;
    }}
    .q-dialog__inner > .q-card {{
        border-radius: 22px !important;
        box-shadow: 0 28px 80px rgba(15, 23, 42, .25) !important;
    }}
    .chart-card {{
        min-height: 340px;
    }}
    .action-tile {{
        transition: transform .2s ease, box-shadow .2s ease;
    }}
    .action-tile:hover {{
        transform: translateY(-5px);
        box-shadow: 0 20px 50px rgba(15, 23, 42, .14);
    }}
    .floating-order {{
        box-shadow: 0 16px 32px rgba(13, 110, 253, .28) !important;
    }}

    /* Print only the bill area */
    @media print {{
        body * {{ visibility: hidden; }}
        .bill-print-area, .bill-print-area * {{ visibility: visible; }}
        .bill-print-area {{ position: absolute; left: 0; top: 0; width: 100%; border: none !important; box-shadow: none !important; }}
    }}

    @media (max-width: 900px) {{
        .store-shell {{ width: min(100% - 16px, 1500px); }}
        .kpi-card {{ min-height: 128px; }}
        .q-table {{ min-width: 760px; }}
        .responsive-scroll {{ overflow-x: auto; }}
    }}
    @media (max-width: 640px) {{
        .store-shell {{ width: calc(100% - 10px); }}
        .q-header .q-row {{ flex-wrap: wrap; }}
        .page-title {{ font-size: 1.55rem !important; }}
        .kpi-card {{ min-width: 100% !important; max-width: none !important; }}
        .mobile-stack {{ flex-direction: column !important; }}
        .mobile-full {{ width: 100% !important; }}
    }}
    """.format(
        bg=colors['bg'], card=colors['card'], text=colors['text'],
        text_secondary=colors['text_secondary'], border=colors['border'],
        primary=colors['primary'], success=colors['success'],
        warning=colors['warning'], danger=colors['danger']
    )
    ui.add_css(css)

def status_dot(status: str) -> str:
    if status == "In Stock":
        return "🟢 " + status
    elif status == "Low Stock":
        return "🟡 " + status
    elif status == "Out of Stock":
        return "🔴 " + status
    return "⚪ " + str(status)

# =========================================================
# Header
# =========================================================

async def render_header(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.header().classes('w-full px-2 sm:px-4').style(
        f'background: {colors["card"]}eF; border-bottom: 1px solid {colors["border"]};'
    ):
        with ui.row().classes('w-full items-center justify-between gap-4 py-3 store-shell'):
            with ui.row().classes('items-center gap-3 min-w-0'):
                with ui.element('div').classes('w-12 h-12 rounded-2xl flex items-center justify-center').style(
                    f'background: linear-gradient(135deg, {colors["primary"]}, #8b5cf6); color: white; box-shadow: 0 10px 24px rgba(99,102,241,.25);'
                ):
                    ui.icon('storefront', size='28px')
                with ui.column().classes('gap-0 min-w-0'):
                    ui.label(config.STORE_NAME).classes('text-xl sm:text-2xl font-black page-title truncate').style(
                        f'color: {colors["text"]};'
                    )
                    ui.label('Inventory • Orders • Analytics').classes('text-xs sm:text-sm').style(
                        f'color: {colors["text_secondary"]};'
                    )

            with ui.row().classes('items-center gap-3'):
                with ui.column().classes('items-end gap-0'):
                    ui.label(i18n.t('total_records')).classes('text-[10px] uppercase tracking-wider font-bold').style(
                        f'color: {colors["text_secondary"]};'
                    )
                    state.lbl_total = ui.label("0").classes('text-lg font-black').style(
                        f'color: {colors["text"]};'
                    )
                with ui.element('div').classes('h-9 w-px').style(f'background:{colors["border"]};'):
                    pass
                with ui.column().classes('items-end gap-0'):
                    ui.label(i18n.t('last_updated')).classes('text-[10px] uppercase tracking-wider font-bold').style(
                        f'color: {colors["text_secondary"]};'
                    )
                    state.lbl_updated = ui.label(format_date_short(state.last_updated)).classes('text-sm font-semibold').style(
                        f'color: {colors["text"]};'
                    )
                with ui.row().classes('items-center gap-1'):
                    ui.button('EN', on_click=lambda: switch_language(state, 'en')).props('dense flat').classes('text-xs font-bold')
                    ui.button('UR', on_click=lambda: switch_language(state, 'ur')).props('dense flat').classes('text-xs font-bold')
                    ui.button(
                        icon='dark_mode' if state.theme == 'light' else 'light_mode',
                        on_click=lambda: toggle_theme(state)
                    ).props('flat dense round').classes('bordered')

    await update_header_stats(state)

async def update_header_stats(state: AppState) -> None:
    try:
        state.total_records = await AdminQueries.get_total_record_count()
        if state.lbl_total:
            state.lbl_total.set_text(format_number(state.total_records))
        if state.lbl_updated:
            state.lbl_updated.set_text(format_date_short(state.last_updated))
    except Exception as e:
        logger.error(f"Header stats error: {e}")

def toggle_theme(state: AppState) -> None:
    state.theme = "dark" if state.theme == "light" else "light"
    apply_theme(state)
    ui.notify(i18n.t('dark_mode') if state.theme == 'dark' else i18n.t('light_mode'), type='info')
    asyncio.create_task(state.refresh_all())

def switch_language(state: AppState, lang: str) -> None:
    state.set_language(lang)
    ui.notify(f"Language: {'English' if lang == 'en' else 'Urdu'}", type='info')

# =========================================================
# Dashboard Tab
# =========================================================

async def render_dashboard(state: AppState) -> None:
    with ui.column().classes('w-full store-shell py-5 sm:py-7 px-1 gap-5'):
        with ui.row().classes('w-full items-end justify-between gap-4 mobile-stack'):
            with ui.column().classes('gap-1'):
                ui.label('Store Command Center').classes('text-3xl sm:text-4xl font-black page-title').style(
                    f'color: {get_theme_colors(state.theme)["text"]};'
                )
                ui.label('Monitor inventory, sales, orders, suppliers and business performance in one place.').classes(
                    'text-sm sm:text-base'
                ).style(f'color: {get_theme_colors(state.theme)["text_secondary"]};')
            with ui.element('div').classes('status-pill flex items-center gap-2'):
                ui.icon('circle', size='9px').style(f'color:{get_theme_colors(state.theme)["success"]};')
                ui.label('LIVE • Auto-refresh every 30s').classes('font-semibold').style(
                    f'color:{get_theme_colors(state.theme)["text"]};'
                )

        await render_kpi_cards(state)

        with ui.card().classes('w-full glass-card p-3 sm:p-4'):
            with ui.row().classes('w-full items-center justify-between gap-3 mobile-stack'):
                with ui.column().classes('gap-0'):
                    ui.label('Analytics Period').classes('section-title text-base sm:text-lg').style(
                        f'color:{get_theme_colors(state.theme)["text"]};'
                    )
                    ui.label('Use the date range below to focus the order summary and related analysis.').classes(
                        'section-subtitle'
                    )
                await render_date_filters(state)

        await render_inventory_table(state)
        await render_order_summary_table(state)
        await render_supplier_table(state)

        with ui.row().classes('w-full items-center gap-2 pt-1'):
            ui.label('Performance Analytics').classes('text-2xl font-black page-title').style(
                f'color:{get_theme_colors(state.theme)["text"]};'
            )
            ui.label('Live database insights').classes('text-sm font-medium').style(
                f'color:{get_theme_colors(state.theme)["text_secondary"]};'
            )

        await render_charts(state)

async def render_kpi_cards(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.row().classes('w-full gap-4 mobile-stack'):
        with ui.card().classes('flex-1 min-w-[230px] p-5 kpi-card glass-card'):
            with ui.row().classes('w-full items-start justify-between'):
                with ui.element('div').classes('kpi-icon').style(
                    f'background: {colors["primary"]}18; color: {colors["primary"]};'
                ):
                    ui.icon('shopping_cart', size='28px')
                ui.icon('trending_up', size='20px').style(f'color:{colors["success"]};')
            with ui.column().classes('gap-0 mt-4'):
                ui.label(i18n.t('total_orders')).classes('text-xs font-bold uppercase tracking-wider').style(
                    f'color:{colors["text_secondary"]};'
                )
                state.kpi_orders = ui.label("0").classes('text-3xl font-black mt-1').style(
                    f'color:{colors["text"]};'
                )

        with ui.card().classes('flex-1 min-w-[230px] p-5 kpi-card glass-card'):
            with ui.row().classes('w-full items-start justify-between'):
                with ui.element('div').classes('kpi-icon').style(
                    f'background: {colors["success"]}18; color: {colors["success"]};'
                ):
                    ui.icon('payments', size='28px')
                ui.icon('show_chart', size='20px').style(f'color:{colors["success"]};')
            with ui.column().classes('gap-0 mt-4'):
                ui.label(i18n.t('total_sales')).classes('text-xs font-bold uppercase tracking-wider').style(
                    f'color:{colors["text_secondary"]};'
                )
                state.kpi_sales = ui.label("0").classes('text-3xl font-black mt-1').style(
                    f'color:{colors["text"]};'
                )

        with ui.card().classes('flex-1 min-w-[230px] p-5 kpi-card glass-card'):
            with ui.row().classes('w-full items-start justify-between'):
                with ui.element('div').classes('kpi-icon').style(
                    f'background: {colors["warning"]}18; color: {colors["warning"]};'
                ):
                    ui.icon('inventory_2', size='28px')
                ui.icon('inventory', size='20px').style(f'color:{colors["warning"]};')
            with ui.column().classes('gap-0 mt-4'):
                ui.label(i18n.t('stock_value')).classes('text-xs font-bold uppercase tracking-wider').style(
                    f'color:{colors["text_secondary"]};'
                )
                state.kpi_stock = ui.label("0").classes('text-3xl font-black mt-1').style(
                    f'color:{colors["text"]};'
                )

    async def refresh_kpi():
        try:
            total_orders = await OrderQueries.get_total_orders()
            total_sales = await OrderQueries.get_total_sales()
            stock_value = await OrderQueries.get_stock_value()
            if state.kpi_orders:
                state.kpi_orders.set_text(format_number(total_orders))
            if state.kpi_sales:
                state.kpi_sales.set_text(format_currency(total_sales))
            if state.kpi_stock:
                state.kpi_stock.set_text(format_currency(stock_value))
        except Exception as e:
            logger.error(f"KPI update error: {e}")

    state.register_refresh(refresh_kpi)
    await refresh_kpi()

async def render_date_filters(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    start_default, end_default = get_current_month_range()
    state.date_start = start_default
    state.date_end = end_default
    with ui.row().classes('items-center gap-2 sm:gap-3 mobile-stack'):
        with ui.row().classes('items-center gap-2'):
            with ui.element('div').classes('w-9 h-9 rounded-xl flex items-center justify-center').style(
                f'background:{colors["primary"]}14; color:{colors["primary"]};'
            ):
                ui.icon('calendar_month', size='19px')
            ui.label(i18n.t('filter')).classes('text-sm font-bold').style(f'color:{colors["text"]};')
        inp_start = ui.input(i18n.t('start_date'), value=start_default).props('type=date outlined').classes('w-40 mobile-full')
        inp_end = ui.input(i18n.t('end_date'), value=end_default).props('type=date outlined').classes('w-40 mobile-full')

        def on_apply():
            state.date_start = inp_start.value or ""
            state.date_end = inp_end.value or ""
            ui.notify(f"Filter: {state.date_start} to {state.date_end}", type='info')
            asyncio.create_task(state.refresh_all())

        def on_reset():
            start_default, end_default = get_current_month_range()
            state.date_start = start_default
            state.date_end = end_default
            inp_start.set_value(start_default)
            inp_end.set_value(end_default)
            ui.notify(i18n.t('reset'), type='info')
            asyncio.create_task(state.refresh_all())

        ui.button(i18n.t('apply'), icon='filter_alt', on_click=on_apply).props('unelevated').classes('bg-primary text-white')
        ui.button(i18n.t('reset'), icon='restart_alt', on_click=on_reset).props('flat')

async def render_inventory_table(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.card().classes('w-full section-card'):
        with ui.row().classes('w-full items-center justify-between p-4 gap-3 mobile-stack'):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-10 h-10 rounded-xl flex items-center justify-center').style(
                    f'background:{colors["primary"]}14; color:{colors["primary"]};'
                ):
                    ui.icon('inventory_2', size='21px')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t('inventory')).classes('text-lg font-black').style(f'color:{colors["text"]};')
                    ui.label('Current stock position and pricing').classes('section-subtitle')
            with ui.row().classes('gap-2 w-auto mobile-full'):
                state.inv_search = ui.input(i18n.t('search'), placeholder='Search products...').props(
                    'dense outlined clearable'
                ).classes('w-64 mobile-full')
                ui.button(i18n.t('refresh'), icon='refresh', on_click=lambda: asyncio.create_task(refresh_inventory(state))).props(
                    'unelevated'
                ).classes('bg-primary text-white')

        with ui.element('div').classes('w-full responsive-scroll px-4 pb-4'):
            cols = [
                {'name': 'product_name', 'label': i18n.t('product_name'), 'field': 'product_name', 'align': 'left'},
                {'name': 'product_category', 'label': i18n.t('product_category'), 'field': 'product_category', 'align': 'left'},
                {'name': 'quantity', 'label': i18n.t('quantity'), 'field': 'quantity', 'align': 'right'},
                {'name': 'stock_price', 'label': i18n.t('stock_price'), 'field': 'stock_price', 'align': 'right'},
                {'name': 'product_price', 'label': i18n.t('product_price'), 'field': 'product_price', 'align': 'right'},
                {'name': 'stock_status', 'label': i18n.t('stock_status'), 'field': 'stock_status', 'align': 'center'},
            ]
            state.inv_table = ui.table(columns=cols, rows=[], row_key='product_name', pagination=10).classes('w-full')

    async def refresh_inventory(state: AppState):
        try:
            search = state.inv_search.value if state.inv_search else None
            rows, total = await InventoryQueries.get_inventory_status(search=search, limit=100, offset=0)
            table_rows = []
            for r in rows:
                table_rows.append({
                    'product_name': r['product_name'],
                    'product_category': r['product_category'],
                    'quantity': format_number(r['quantity']),
                    'stock_price': format_currency(r['stock_price']),
                    'product_price': format_currency(r['product_price']),
                    'stock_status': status_dot(r['stock_status']),
                })
            if state.inv_table:
                state.inv_table.rows = table_rows
                state.inv_table.update()
        except Exception as e:
            logger.error(f"Inventory table error: {e}")

    state.register_refresh(lambda: refresh_inventory(state))
    await refresh_inventory(state)

async def render_order_summary_table(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.card().classes('w-full section-card'):
        with ui.row().classes('w-full items-center justify-between p-4'):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-10 h-10 rounded-xl flex items-center justify-center').style(
                    f'background:{colors["success"]}14; color:{colors["success"]};'
                ):
                    ui.icon('receipt_long', size='21px')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t('orders')).classes('text-lg font-black').style(f'color:{colors["text"]};')
                    ui.label('Daily order activity').classes('section-subtitle')
            ui.button(i18n.t('refresh'), icon='refresh', on_click=lambda: asyncio.create_task(refresh_orders(state))).props(
                'unelevated'
            ).classes('bg-success text-white')

        with ui.element('div').classes('w-full responsive-scroll px-4 pb-4'):
            cols = [
                {'name': 'order_date', 'label': i18n.t('order_date'), 'field': 'order_date', 'align': 'left'},
                {'name': 'total_orders', 'label': i18n.t('total_orders'), 'field': 'total_orders', 'align': 'right'},
                {'name': 'total_orders_price', 'label': i18n.t('total_orders_price'), 'field': 'total_orders_price', 'align': 'right'},
            ]
            state.order_table = ui.table(columns=cols, rows=[], row_key='order_date', pagination=10).classes('w-full')

    async def refresh_orders(state: AppState):
        try:
            rows, total = await OrderQueries.get_orders_summary(
                start_date=state.date_start or None,
                end_date=state.date_end or None,
                limit=100, offset=0
            )
            table_rows = []
            for r in rows:
                table_rows.append({
                    'order_date': format_date_short(r['order_date']),
                    'total_orders': format_number(r['total_orders']),
                    'total_orders_price': format_currency(r['total_orders_price']),
                })
            if state.order_table:
                state.order_table.rows = table_rows
                state.order_table.update()
        except Exception as e:
            logger.error(f"Order summary error: {e}")

    state.register_refresh(lambda: refresh_orders(state))
    await refresh_orders(state)

async def render_supplier_table(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.card().classes('w-full section-card'):
        with ui.row().classes('w-full items-center justify-between p-4 gap-3 mobile-stack'):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-10 h-10 rounded-xl flex items-center justify-center').style(
                    f'background:{colors["warning"]}18; color:{colors["warning"]};'
                ):
                    ui.icon('local_shipping', size='21px')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t('suppliers')).classes('text-lg font-black').style(f'color:{colors["text"]};')
                    ui.label('Supplier availability and stock coverage').classes('section-subtitle')
            with ui.row().classes('gap-2 mobile-full'):
                state.sup_search = ui.input(i18n.t('search'), placeholder='Search suppliers...').props(
                    'dense outlined clearable'
                ).classes('w-64 mobile-full')
                ui.button(i18n.t('refresh'), icon='refresh', on_click=lambda: asyncio.create_task(refresh_suppliers(state))).props(
                    'unelevated'
                ).classes('bg-warning text-white')

        with ui.element('div').classes('w-full responsive-scroll px-4 pb-4'):
            cols = [
                {'name': 'supplier_name', 'label': i18n.t('supplier_name'), 'field': 'supplier_name', 'align': 'left'},
                {'name': 'product_category', 'label': i18n.t('product_category'), 'field': 'product_category', 'align': 'left'},
                {'name': 'stock_status', 'label': i18n.t('stock_status'), 'field': 'stock_status', 'align': 'center'},
                {'name': 'stock_quantity', 'label': i18n.t('stock_quantity'), 'field': 'stock_quantity', 'align': 'right'},
                {'name': 'supplier_number', 'label': i18n.t('supplier_number'), 'field': 'supplier_number', 'align': 'left'},
            ]
            state.sup_table = ui.table(columns=cols, rows=[], row_key='supplier_name', pagination=10).classes('w-full')

    async def refresh_suppliers(state: AppState):
        try:
            search = state.sup_search.value if state.sup_search else None
            rows, total = await SupplierQueries.get_suppliers(search=search, limit=100, offset=0)
            table_rows = []
            for r in rows:
                table_rows.append({
                    'supplier_name': r['supplier_name'],
                    'product_category': r['product_category'] or '—',
                    'stock_status': status_dot(r['stock_status'] or 'N/A'),
                    'stock_quantity': format_number(r['stock_quantity'] or 0),
                    'supplier_number': r['supplier_number'],
                })
            if state.sup_table:
                state.sup_table.rows = table_rows
                state.sup_table.update()
        except Exception as e:
            logger.error(f"Supplier table error: {e}")

    state.register_refresh(lambda: refresh_suppliers(state))
    await refresh_suppliers(state)

def empty_figure() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(font_size=12),
    )
    return fig

async def render_charts(state: AppState) -> None:
    colors = get_theme_colors(state.theme)

    chart_specs = [
        ('sales_trend', 'query_stats', 'Sales Trend', 'Revenue over the last 30 days'),
        ('order_trend', 'event_note', 'Order Trend', 'Daily order volume'),
        ('product_performance', 'star', 'Product Performance', 'Top products by revenue'),
        ('stock_status_dist', 'pie_chart', 'Stock Status', 'Current inventory distribution'),
        ('category_performance', 'category', 'Category Performance', 'Revenue by product category'),
        ('dual', 'insights', 'Sales vs Orders Volume', 'Revenue and order volume together'),
    ]
    with ui.row().classes('w-full gap-4 mobile-stack'):
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[0][1], size='19px').style(f'color:{colors["primary"]};')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t(chart_specs[0][0])).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label(chart_specs[0][3]).classes('section-subtitle')
            state.chart_sales = ui.plotly(empty_figure()).classes('w-full h-72')
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[1][1], size='19px').style(f'color:{colors["success"]};')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t(chart_specs[1][0])).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label(chart_specs[1][3]).classes('section-subtitle')
            state.chart_orders = ui.plotly(empty_figure()).classes('w-full h-72')

    with ui.row().classes('w-full gap-4 mobile-stack'):
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[2][1], size='19px').style(f'color:{colors["warning"]};')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t(chart_specs[2][0])).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label(chart_specs[2][3]).classes('section-subtitle')
            state.chart_products = ui.plotly(empty_figure()).classes('w-full h-72')
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[3][1], size='19px').style(f'color:{colors["danger"]};')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t(chart_specs[3][0])).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label('Healthy, low and out-of-stock mix').classes('section-subtitle')
            state.chart_stock = ui.plotly(empty_figure()).classes('w-full h-72')

    with ui.row().classes('w-full gap-4 mobile-stack'):
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[4][1], size='19px').style(f'color:#6f42c1;')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t(chart_specs[4][0])).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label(chart_specs[4][3]).classes('section-subtitle')
            state.chart_categories = ui.plotly(empty_figure()).classes('w-full h-72')
        with ui.card().classes('flex-1 min-w-[300px] chart-card section-card p-3'):
            with ui.row().classes('items-center gap-2 px-2 pt-1'):
                ui.icon(chart_specs[5][1], size='19px').style(f'color:{colors["primary"]};')
                with ui.column().classes('gap-0'):
                    ui.label(chart_specs[5][2]).classes('text-base font-black').style(f'color:{colors["text"]};')
                    ui.label(chart_specs[5][3]).classes('section-subtitle')
            state.chart_dual = ui.plotly(empty_figure()).classes('w-full h-72')

    async def refresh_charts():
        colors = get_theme_colors(state.theme)
        text_color = colors["text"]
        grid_color = colors["grid"]
        try:
            sales_data = await AnalyticsQueries.get_sales_trend(30)
            dates = [format_date_short(r['order_date']) for r in sales_data]
            revenues = [float(r['total_orders_price'] or 0) for r in sales_data]
            order_counts = [int(r['total_orders'] or 0) for r in sales_data]

            fig_sales = go.Figure()
            fig_sales.add_trace(go.Scatter(
                x=dates, y=revenues, mode='lines+markers',
                name='Revenue', line=dict(color='#0d6efd', width=3, shape='spline'),
                marker=dict(size=6),
                fill='tozeroy', fillcolor='rgba(13,110,253,0.08)'
            ))
            fig_sales.update_layout(
                margin=dict(l=10, r=10, t=12, b=20),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                xaxis=dict(gridcolor=grid_color, showline=False, tickangle=-35),
                yaxis=dict(gridcolor=grid_color, title='Revenue', zeroline=False),
                showlegend=False, height=280,
                hovermode='x unified',
            )
            if state.chart_sales:
                state.chart_sales.update_figure(fig_sales)

            fig_orders = go.Figure()
            fig_orders.add_trace(go.Bar(
                x=dates, y=order_counts, marker_color='#198754', name='Orders',
                marker_line_width=0, opacity=.9
            ))
            fig_orders.update_layout(
                margin=dict(l=10, r=10, t=12, b=20),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                xaxis=dict(gridcolor=grid_color, tickangle=-35),
                yaxis=dict(gridcolor=grid_color, title='Order Count', zeroline=False),
                showlegend=False, height=280,
                bargap=.18,
            )
            if state.chart_orders:
                state.chart_orders.update_figure(fig_orders)

            prod_data = await AnalyticsQueries.get_product_performance(10)
            prod_names = [r['product_name'][:20] for r in prod_data]
            prod_revenue = [float(r['revenue'] or 0) for r in prod_data]
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Bar(
                x=prod_names, y=prod_revenue, marker_color='#fd7e14',
                marker_line_width=0, opacity=.92
            ))
            fig_prod.update_layout(
                margin=dict(l=10, r=10, t=12, b=55),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                xaxis=dict(gridcolor=grid_color, tickangle=-30),
                yaxis=dict(gridcolor=grid_color, zeroline=False),
                showlegend=False, height=280,
            )
            if state.chart_products:
                state.chart_products.update_figure(fig_prod)

            stock_data = await AnalyticsQueries.get_stock_distribution()
            labels = [r['stock_status'] for r in stock_data]
            values = [int(r['count'] or 0) for r in stock_data]
            pie_colors = ['#198754', '#ffc107', '#dc3545']
            fig_stock = go.Figure(data=[go.Pie(
                labels=labels, values=values, marker_colors=pie_colors,
                hole=0.58, textinfo='label+percent', textfont=dict(size=10),
                pull=[0.03] * len(labels)
            )])
            fig_stock.update_layout(
                margin=dict(l=10, r=10, t=10, b=15),
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                showlegend=True,
                legend=dict(orientation='h', yanchor='bottom', y=-0.12),
                height=280,
            )
            if state.chart_stock:
                state.chart_stock.update_figure(fig_stock)

            cat_data = await AnalyticsQueries.get_category_performance()
            cat_names = [r['category_name'] for r in cat_data]
            cat_revenue = [float(r['revenue'] or 0) for r in cat_data]
            fig_cat = go.Figure()
            fig_cat.add_trace(go.Bar(
                x=cat_names, y=cat_revenue, marker_color='#6f42c1',
                marker_line_width=0, opacity=.92
            ))
            fig_cat.update_layout(
                margin=dict(l=10, r=10, t=12, b=40),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                xaxis=dict(gridcolor=grid_color),
                yaxis=dict(gridcolor=grid_color, zeroline=False),
                showlegend=False, height=280,
            )
            if state.chart_categories:
                state.chart_categories.update_figure(fig_cat)

            fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
            fig_dual.add_trace(
                go.Scatter(x=dates, y=revenues, name="Revenue", line=dict(color='#0d6efd', width=3, shape='spline')),
                secondary_y=False
            )
            fig_dual.add_trace(
                go.Scatter(x=dates, y=order_counts, name="Orders", line=dict(color='#dc3545', width=3), mode='lines+markers'),
                secondary_y=True
            )
            fig_dual.update_layout(
                margin=dict(l=10, r=10, t=12, b=20),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color, size=10),
                xaxis=dict(gridcolor=grid_color, tickangle=-35),
                height=280,
                legend=dict(orientation='h', yanchor='bottom', y=-0.2),
                hovermode='x unified',
            )
            fig_dual.update_yaxes(title_text="Revenue", secondary_y=False, gridcolor=grid_color, zeroline=False)
            fig_dual.update_yaxes(title_text="Order Count", secondary_y=True, gridcolor=grid_color, zeroline=False)
            if state.chart_dual:
                state.chart_dual.update_figure(fig_dual)

        except Exception as e:
            logger.error(f"Chart update error: {e}")

    state.register_refresh(refresh_charts)
    await refresh_charts()

async def render_order_tab(state: AppState) -> None:
    colors = get_theme_colors(state.theme)
    with ui.column().classes('w-full store-shell py-8 sm:py-12 px-2 gap-7 items-center'):
        with ui.column().classes('items-center gap-2 text-center'):
            with ui.element('div').classes('w-16 h-16 rounded-3xl flex items-center justify-center').style(
                f'background: linear-gradient(135deg, {colors["primary"]}, #8b5cf6); color:white; box-shadow:0 14px 34px rgba(99,102,241,.22);'
            ):
                ui.icon('shopping_bag', size='32px')
            ui.label(i18n.t('order_update')).classes('text-3xl sm:text-4xl font-black page-title').style(
                f'color:{colors["text"]};'
            )
            ui.label('Fast, focused actions for your daily store operations.').classes('text-sm sm:text-base').style(
                f'color:{colors["text_secondary"]};'
            )

        with ui.row().classes('w-full gap-5 justify-center mobile-stack'):
            with ui.card().classes('flex-1 max-w-md min-h-[230px] cursor-pointer action-tile section-card').style(
                f'background:{colors["card"]}; border:1px solid {colors["primary"]}55;'
            ):
                async def open_order():
                    await open_place_order_dialog(state)
                with ui.column().classes('w-full h-full p-7 justify-center items-start gap-4').on('click', open_order):
                    with ui.element('div').classes('w-14 h-14 rounded-2xl flex items-center justify-center').style(
                        f'background:{colors["primary"]}16; color:{colors["primary"]};'
                    ):
                        ui.icon('add_shopping_cart', size='30px')
                    ui.label(i18n.t('place_new_order')).classes('text-2xl font-black').style(f'color:{colors["text"]};')
                    ui.label('Build a multi-item cart, preview the bill, and complete the order in one flow.').classes(
                        'text-sm leading-relaxed'
                    ).style(f'color:{colors["text_secondary"]};')
                    with ui.row().classes('items-center gap-1'):
                        ui.label('Start order').classes('text-sm font-bold').style(f'color:{colors["primary"]};')
                        ui.icon('arrow_forward', size='18px').style(f'color:{colors["primary"]};')

            with ui.card().classes('flex-1 max-w-md min-h-[230px] cursor-pointer action-tile section-card').style(
                f'background:{colors["card"]}; border:1px solid {colors["success"]}55;'
            ):
                async def open_admin():
                    await open_edit_database_dialog(state)
                with ui.column().classes('w-full h-full p-7 justify-center items-start gap-4').on('click', open_admin):
                    with ui.element('div').classes('w-14 h-14 rounded-2xl flex items-center justify-center').style(
                        f'background:{colors["success"]}16; color:{colors["success"]};'
                    ):
                        ui.icon('admin_panel_settings', size='30px')
                    ui.label(i18n.t('edit_database')).classes('text-2xl font-black').style(f'color:{colors["text"]};')
                    ui.label('Manage products, suppliers, categories, inventory and order records.').classes(
                        'text-sm leading-relaxed'
                    ).style(f'color:{colors["text_secondary"]};')
                    with ui.row().classes('items-center gap-1'):
                        ui.label('Open database tools').classes('text-sm font-bold').style(f'color:{colors["success"]};')
                        ui.icon('arrow_forward', size='18px').style(f'color:{colors["success"]};')

async def open_place_order_dialog(state: AppState) -> None:
    """Open professional order placement modal with multiple items (cart)."""
    colors = get_theme_colors(state.theme)

    # Fetch products
    products, _ = await ProductQueries.get_products(active_only=True, limit=1000, offset=0)
    product_options = {str(r['product_id']): f"{r['product_name']} ({r['category_name']}) - Rs. {r['product_price']}" for r in products}
    product_map = {str(r['product_id']): dict(r) for r in products}

    # Cart state (list of dicts)
    cart: List[Dict] = []

    with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-6xl mx-auto section-card').style(f'background: {colors["card"]};'):
        with ui.row().classes('w-full items-center justify-between p-5'):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-11 h-11 rounded-xl flex items-center justify-center').style(
                    f'background:{colors["primary"]}16; color:{colors["primary"]};'
                ):
                    ui.icon('shopping_cart', size='23px')
                with ui.column().classes('gap-0'):
                    ui.label(i18n.t('place_new_order')).classes('text-xl font-black').style(f'color:{colors["text"]};')
                    ui.label('Build order • Review cart • Print bill').classes('text-xs').style(f'color:{colors["text_secondary"]};')
            ui.button(icon='close', on_click=dialog.close).props('flat dense')

        with ui.row().classes('w-full gap-4'):
            # Left: Product selection
            with ui.column().classes('flex-1 min-w-[300px] gap-3 p-4').style(f'border-right: 1px solid {colors["border"]};'):
                ui.label(i18n.t('product')).classes('text-md font-bold').style(f'color: {colors["text_secondary"]};')

                sel_product = ui.select(
                    label='Product',
                    options=product_options,
                    with_input=True,
                    clearable=True,
                ).props('outlined dense').classes('w-full')

                lbl_category = ui.label(f"{i18n.t('category')}: —").classes('text-sm').style(f'color: {colors["text"]};')
                lbl_price = ui.label(f"{i18n.t('current_price')}: —").classes('text-sm').style(f'color: {colors["text"]};')
                lbl_available = ui.label(f"{i18n.t('available_quantity')}: —").classes('text-sm').style(f'color: {colors["text"]};')

                inp_quantity = ui.number(i18n.t('quantity'), value=1, min=1).props('outlined dense').classes('w-full')
                inp_unit_price = ui.number(i18n.t('unit_price'), value=0, min=0, format='%.2f').props('outlined dense').classes('w-full')

                ui.button('Add to Cart', icon='add_shopping_cart', on_click=lambda: add_to_cart()).props('unelevated').classes('bg-primary text-white')

                inp_order_date = ui.input(i18n.t('order_date'), value=datetime.now().strftime('%Y-%m-%d')).props('type=date outlined dense').classes('w-full')
                inp_notes = ui.input(i18n.t('notes')).props('outlined dense').classes('w-full')

                order_error = ui.label('').classes('text-negative text-sm')

            # Right: Cart & Bill Preview
            with ui.column().classes('flex-1 min-w-[300px] gap-3 p-4'):
                ui.label('Cart Items').classes('text-md font-bold').style(f'color: {colors["text_secondary"]};')
                cart_container = ui.column().classes('w-full gap-2 max-h-48 overflow-y-auto')

                lbl_grand_total = ui.label(f"{i18n.t('total_amount')}: {format_currency(0)}").classes('text-xl font-bold').style(f'color: {colors["primary"]};')

                ui.label('Bill Preview').classes('text-md font-bold').style(f'color: {colors["text_secondary"]};')
                bill_card = ui.card().classes('w-full p-5 bill-print-area').style('background: #fff; color: #000; border: 1px dashed #a3a3a3; border-radius:14px; box-shadow: 0 12px 28px rgba(0,0,0,.08);')
                with bill_card:
                    bill_html = ui.html(render_bill_html('—', '—', 0, 0, 0, 'PENDING')).classes('w-full')

                with ui.row().classes('w-full gap-2'):
                    ui.button(i18n.t('place_order'), icon='check', on_click=lambda: submit_order()).props('unelevated').classes('bg-primary text-white')
                    ui.button(i18n.t('cancel'), on_click=dialog.close).props('flat')
                    ui.button(i18n.t('print_bill'), icon='print', on_click=lambda: ui.run_javascript('window.print()')).props('outline dense')

        # Helper functions
        def update_bill():
            if cart:
                items_html = ""
                total = 0
                for item in cart:
                    line_total = item['quantity'] * item['unit_price']
                    total += line_total
                    items_html += f"<tr><td>{item['product_name'][:18]}</td><td>{item['quantity']}</td><td>{format_currency(item['unit_price'], symbol=False)}</td><td style='text-align:right'>{format_currency(line_total, symbol=False)}</td></tr>"
                html = f"""
                <div style="font-family: 'Courier New', monospace; text-align: center; line-height: 1.5; font-size: 12px;">
                    <h3 style="margin:0; font-size: 15px; font-weight: bold;">{config.STORE_NAME}</h3>
                    <p style="margin:4px 0; color: #666;">Retail Invoice</p>
                    <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
                    <p style="text-align: left; margin: 2px 0;"><strong>Order #:</strong> PENDING</p>
                    <p style="text-align: left; margin: 2px 0;"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                    <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
                    <table style="width: 100%; text-align: left; font-size: 11px;">
                        <tr style="font-weight: bold; border-bottom: 1px solid #ccc;">
                            <td>Item</td><td>Qty</td><td>Price</td><td style="text-align:right">Total</td>
                        </tr>
                        {items_html}
                    </table>
                    <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
                    <p style="text-align: right; font-size: 13px; font-weight: bold;">
                        Grand Total: {format_currency(total)}
                    </p>
                    <p style="color: #666; margin-top: 8px; font-size: 10px;">Thank you for your business!</p>
                </div>
                """
                bill_html.set_content(html)
                lbl_grand_total.set_text(f"{i18n.t('total_amount')}: {format_currency(total)}")
            else:
                bill_html.set_content(render_bill_html('—', '—', 0, 0, 0, 'PENDING'))
                lbl_grand_total.set_text(f"{i18n.t('total_amount')}: {format_currency(0)}")

        def refresh_cart_ui():
            cart_container.clear()
            with cart_container:
                for item in cart:
                    with ui.row().classes('w-full items-center justify-between border rounded p-2'):
                        ui.label(f"{item['product_name']} x {item['quantity']} = {format_currency(item['line_total'])}").classes('text-sm')
                        ui.button(icon='delete', on_click=lambda pid=item['product_id']: remove_item(pid)).props('flat dense color-negative')

        def add_to_cart():
            order_error.set_text('')
            pid = sel_product.value
            if not pid:
                order_error.set_text("Please select a product")
                return
            quantity = int(inp_quantity.value or 0)
            if quantity <= 0:
                order_error.set_text("Quantity must be > 0")
                return
            unit_price = float(inp_unit_price.value or 0)
            if unit_price < 0:
                order_error.set_text("Invalid price")
                return
            # Check stock
            p = product_map.get(pid)
            if p and p['quantity'] is not None and p['quantity'] < quantity:
                order_error.set_text(f"Insufficient stock for {p['product_name']}")
                return
            # Add or update
            for item in cart:
                if item['product_id'] == int(pid):
                    item['quantity'] += quantity
                    item['line_total'] = item['quantity'] * item['unit_price']
                    break
            else:
                cart.append({
                    'product_id': int(pid),
                    'product_name': p['product_name'],
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_total': quantity * unit_price
                })
            refresh_cart_ui()
            update_bill()

        def remove_item(pid):
            nonlocal cart
            cart = [item for item in cart if item['product_id'] != pid]
            refresh_cart_ui()
            update_bill()

        refresh_cart_ui()
        update_bill()

        # Product selection handler
        async def on_product_change(e):
            pid = e.value
            if pid and pid in product_map:
                p = product_map[pid]
                lbl_category.set_text(f"{i18n.t('category')}: {p['category_name']}")
                lbl_price.set_text(f"{i18n.t('current_price')}: {format_currency(p['product_price'])}")
                lbl_available.set_text(f"{i18n.t('available_quantity')}: {format_number(p['quantity'])}")
                inp_unit_price.set_value(float(p['product_price']))
            else:
                lbl_category.set_text(f"{i18n.t('category')}: —")
                lbl_price.set_text(f"{i18n.t('current_price')}: —")
                lbl_available.set_text(f"{i18n.t('available_quantity')}: —")

        sel_product.on_value_change(on_product_change)

        # Submit order
        async def submit_order():
            order_error.set_text('')
            if not cart:
                order_error.set_text("Cart is empty")
                return
            order_date_str = inp_order_date.value or datetime.now().strftime('%Y-%m-%d')
            try:
                order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date()
            except:
                order_date = datetime.now().date()
            notes = inp_notes.value or None
            items = [{'product_id': item['product_id'], 'quantity': item['quantity'], 'unit_price': item['unit_price']} for item in cart]
            try:
                order_id, order_number = await OrderQueries.place_order_multi(items, order_date, notes)
                await AnalyticsQueries.refresh_materialized_views()
                dialog.close()
                ui.notify(f"{i18n.t('order_placed')}: {order_number}", type='positive', position='top')
                # Show bill popup with items info
                await show_bill_popup(state, order_number, cart, order_date)
                await state.refresh_all()
            except Exception as e:
                error_msg = str(e)
                if "Insufficient stock" in error_msg:
                    order_error.set_text(i18n.t('insufficient_stock'))
                else:
                    order_error.set_text(f"Error: {error_msg}")
                logger.error(f"Order submission error: {e}")

    dialog.open()

def render_bill_html(product_name, category, qty, unit_price, total, order_number) -> str:
    return f"""
    <div style="font-family: 'Courier New', monospace; text-align: center; line-height: 1.5; font-size: 12px;">
        <h3 style="margin:0; font-size: 15px; font-weight: bold;">{config.STORE_NAME}</h3>
        <p style="margin:4px 0; color: #666;">Retail Invoice</p>
        <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
        <p style="text-align: left; margin: 2px 0;"><strong>Order #:</strong> {order_number}</p>
        <p style="text-align: left; margin: 2px 0;"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
        <table style="width: 100%; text-align: left; font-size: 11px;">
            <tr style="font-weight: bold; border-bottom: 1px solid #ccc;">
                <td>Item</td><td>Qty</td><td>Price</td><td style="text-align:right">Total</td>
            </tr>
            <tr>
                <td>{(product_name or '—')[:18]}</td>
                <td>{qty or 0}</td>
                <td>{format_currency(unit_price or 0, symbol=False)}</td>
                <td style="text-align:right">{format_currency(total, symbol=False)}</td>
            </tr>
        </table>
        <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
        <p style="text-align: right; font-size: 13px; font-weight: bold;">
            Grand Total: {format_currency(total)}
        </p>
        <p style="color: #666; margin-top: 8px; font-size: 10px;">Thank you for your business!</p>
    </div>
    """

async def show_bill_popup(state: AppState, order_number, items: List[Dict], order_date) -> None:
    """Show a small popup with the final bill after order placement."""
    colors = get_theme_colors(state.theme)
    with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-md mx-auto bill-print-area').style(f'background: #fff; color: #000; border-radius:18px; box-shadow:0 24px 70px rgba(0,0,0,.20);'):
        with ui.row().classes('w-full items-center justify-between p-2'):
            ui.label("Order Confirmed ✓").classes('text-lg font-bold').style('color: #198754;')
            ui.button(icon='close', on_click=dialog.close).props('flat dense')

        # Build HTML for multiple items
        items_html = ""
        total = 0
        for item in items:
            line_total = item['quantity'] * item['unit_price']
            total += line_total
            items_html += f"<tr><td>{item['product_name'][:18]}</td><td>{item['quantity']}</td><td>{format_currency(item['unit_price'], symbol=False)}</td><td style='text-align:right'>{format_currency(line_total, symbol=False)}</td></tr>"
        html = f"""
        <div style="font-family: 'Courier New', monospace; text-align: center; line-height: 1.5; font-size: 12px;">
            <h3 style="margin:0; font-size: 15px; font-weight: bold;">{config.STORE_NAME}</h3>
            <p style="margin:4px 0; color: #666;">Retail Invoice</p>
            <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
            <p style="text-align: left; margin: 2px 0;"><strong>Order #:</strong> {order_number}</p>
            <p style="text-align: left; margin: 2px 0;"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
            <table style="width: 100%; text-align: left; font-size: 11px;">
                <tr style="font-weight: bold; border-bottom: 1px solid #ccc;">
                    <td>Item</td><td>Qty</td><td>Price</td><td style="text-align:right">Total</td>
                </tr>
                {items_html}
            </table>
            <hr style="border: none; border-top: 1px dashed #999; margin: 8px 0;">
            <p style="text-align: right; font-size: 13px; font-weight: bold;">
                Grand Total: {format_currency(total)}
            </p>
            <p style="color: #666; margin-top: 8px; font-size: 10px;">Thank you for your business!</p>
        </div>
        """
        ui.html(html).classes('w-full p-2')

        with ui.row().classes('w-full gap-2 justify-center p-2'):
            ui.button(i18n.t('print_bill'), icon='print', on_click=lambda: ui.run_javascript('window.print()')).props('unelevated').classes('bg-primary text-white')
            ui.button(i18n.t('close'), on_click=dialog.close).props('flat')

    dialog.open()

# =========================================================
# Edit Database Dialog
# =========================================================

async def open_edit_database_dialog(state: AppState) -> None:
    """Open database administration interface with tabs for table selection."""
    try:
        colors = get_theme_colors(state.theme)
        tables = ['products', 'inventory', 'orders', 'order_items', 'suppliers', 'categories']
        state.current_admin_table = 'products'

        with ui.dialog().props('persistent') as dialog, ui.card().classes('w-full max-w-6xl mx-auto h-[90vh]').style(f'background: {colors["card"]};'):
            with ui.row().classes('w-full items-center justify-between p-4'):
                ui.label(i18n.t('edit_database')).classes('text-xl font-bold').style(f'color: {colors["text"]};')
                ui.button(icon='close', on_click=dialog.close).props('flat dense')

            with ui.tabs().classes('w-full') as tabs:
                tab_map = {}
                for tbl in tables:
                    tab_label = tbl.replace('_', ' ').title()
                    tab = ui.tab(tab_label)
                    tab_map[tab_label] = tbl

            state.db_admin_container = ui.element('div').classes('w-full flex-1 overflow-auto p-4')

            async def on_tab_change(e):
                state.current_admin_table = tab_map.get(e.value, 'products')
                await render_admin_table(state)

            tabs.on_value_change(on_tab_change)

            dialog.open()
            await asyncio.sleep(0.1)
            await render_admin_table(state)

    except Exception as e:
        logger.error(f"Edit DB Dialog Error: {e}")
        ui.notify(f"Error opening database editor: {e}", type='negative')

async def render_admin_table(state: AppState) -> None:
    """Render CRUD interface for a database table."""
    colors = get_theme_colors(state.theme)
    if not state.db_admin_container:
        return
    state.db_admin_container.clear()
    table_name = state.current_admin_table

    with state.db_admin_container:
        try:
            columns_info = await AdminQueries.get_table_columns(table_name)
            columns = [c['column_name'] for c in columns_info]
            rows, total = await AdminQueries.get_table_data(table_name, limit=50, offset=0)

            table_columns = [{'name': c, 'label': c, 'field': c, 'align': 'left'} for c in columns]
            table_rows = []
            for r in rows:
                row = dict(r)
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = format_date_short(v)
                    elif isinstance(v, float) and v is not None:
                        row[k] = f"{v:.2f}"
                    elif isinstance(v, dict):
                        row[k] = json.dumps(v)
                    elif v is None:
                        row[k] = "—"
                table_rows.append(row)

            with ui.row().classes('w-full items-center justify-between mb-2'):
                ui.label(f"{table_name.title()} — {total} {i18n.t('records')}").classes('text-md font-bold').style(f'color: {colors["text"]};')
                ui.button(i18n.t('refresh'), icon='refresh', on_click=lambda: asyncio.create_task(render_admin_table(state))).props('dense flat')

            if table_rows:
                ui.table(columns=table_columns, rows=table_rows, row_key=columns[0], pagination=20).classes('w-full')
            else:
                ui.label(i18n.t('no_data')).classes('text-center p-4').style(f'color: {colors["text_secondary"]};')

            if table_name in ['products', 'suppliers', 'categories']:
                with ui.expansion(f"Add New {table_name.title()}", icon='add').classes('w-full mt-4'):
                    await render_add_form(state, table_name, columns_info)

        except Exception as e:
            ui.label(f"Error: {str(e)}").classes('text-negative')
            logger.error(f"DB admin error: {e}")

async def render_add_form(state: AppState, table_name: str, columns_info: List[Dict]) -> None:
    """Render a dynamic add form based on table schema."""
    colors = get_theme_colors(state.theme)
    inputs = {}

    # Extra inputs for products (quantity, stock_price)
    if table_name == 'products':
        inputs['quantity'] = ui.number("Initial Quantity", value=0).props('outlined dense').classes('w-full')
        inputs['stock_price'] = ui.number("Stock Price", value=0.0, format='%.2f').props('outlined dense').classes('w-full')

    # Fetch categories for any table that has a category_id column (but not for categories table)
    categories = []
    if any(col['column_name'] == 'category_id' for col in columns_info) and table_name != 'categories':
        categories = await AdminQueries.get_categories()

    with ui.column().classes('w-full gap-2 p-4').style(f'border: 1px solid {colors["border"]}; border-radius: 8px;'):
        for col in columns_info:
            col_name = col['column_name']
            # Skip system-managed columns
            if col_name in ['product_id', 'inventory_id', 'supplier_id', 'order_id', 'item_id', 'created_at', 'updated_at', 'audit_id', 'transaction_id']:
                continue
            # Skip category_id when adding a new category (it's auto-generated)
            if col_name == 'category_id' and table_name == 'categories':
                continue
            if col_name in inputs:
                continue

            data_type = col['data_type']

            if col_name == 'category_id' and categories:
                options = {str(c['category_id']): c['category_name'] for c in categories}
                inputs[col_name] = ui.select(
                    label='Category',
                    options=options,
                    with_input=True,
                    clearable=False
                ).props('outlined dense').classes('w-full')
                if categories:
                    inputs[col_name].set_value(str(categories[0]['category_id']))
            elif 'int' in data_type and 'serial' not in data_type:
                inputs[col_name] = ui.number(col_name, value=0).props('outlined dense').classes('w-full')
            elif 'numeric' in data_type or 'decimal' in data_type or 'real' in data_type or 'double' in data_type:
                inputs[col_name] = ui.number(col_name, value=0.0, format='%.2f').props('outlined dense').classes('w-full')
            elif 'bool' in data_type:
                inputs[col_name] = ui.checkbox(col_name, value=True)
            elif 'date' in data_type:
                inputs[col_name] = ui.input(col_name, value=datetime.now().strftime('%Y-%m-%d')).props('type=date outlined dense').classes('w-full')
            elif 'json' in data_type:
                inputs[col_name] = ui.input(col_name, value='{}').props('outlined dense').classes('w-full')
            else:
                inputs[col_name] = ui.input(col_name).props('outlined dense').classes('w-full')

        async def do_insert():
            try:
                values = []
                col_names = []
                for col_name, inp in inputs.items():
                    if col_name in ['quantity', 'stock_price']:
                        continue
                    col_names.append(col_name)
                    val = inp.value
                    if col_name == 'category_id':
                        val = int(val) if val else None
                    values.append(val)

                if table_name == 'products':
                    placeholders = ', '.join([f'${i+1}' for i in range(len(values))])
                    query = f"INSERT INTO {table_name} ({', '.join(col_names)}) VALUES ({placeholders}) RETURNING product_id"
                    async with db.transaction() as conn:
                        pid = await conn.fetchval(query, *values)
                        qty = int(inputs.get('quantity').value or 0)
                        stock_price = float(inputs.get('stock_price').value or 0)
                        await conn.execute(
                            "INSERT INTO inventory (product_id, quantity, stock_price, low_stock_threshold) VALUES ($1,$2,$3,$4)",
                            pid, qty, stock_price, config.LOW_STOCK_THRESHOLD
                        )
                else:
                    placeholders = ', '.join([f'${i+1}' for i in range(len(values))])
                    query = f"INSERT INTO {table_name} ({', '.join(col_names)}) VALUES ({placeholders})"
                    await db.execute(query, *values)

                ui.notify(f"Record added to {table_name}", type='positive')
                await render_admin_table(state)
            except Exception as e:
                ui.notify(f"Error: {str(e)}", type='negative')
                logger.error(f"Insert error: {e}")

        ui.button(i18n.t('add'), icon='add', on_click=do_insert).props('unelevated').classes('bg-success text-white')

# =========================================================
# Floating Action Button
# =========================================================

async def render_floating_button(state: AppState) -> None:
    async def on_click():
        await open_place_order_dialog(state)
    with ui.element('div').classes('fixed bottom-6 left-6 z-50'):
        ui.button(i18n.t('place_order'), icon='add_shopping_cart', on_click=on_click).props('round size=lg').classes(
            'bg-primary text-white shadow-lg hover:shadow-xl'
        ).style('border-radius: 28px; padding: 0 24px; height: 56px;')

# =========================================================
# Main Page
# =========================================================

@ui.page('/')
async def main_page():
    logger.info("Application page loaded")
    state = AppState()
    apply_theme(state)

    loading_label = ui.label("Connecting to database...").classes('text-center text-lg p-10 font-semibold')
    ui.update()

    try:
        await db.initialize(max_retries=15, delay=2.0)
        loading_label.set_visibility(False)
        logger.info("Database connected")
    except Exception as e:
        loading_label.set_text(f"Database connection failed: {e}")
        logger.error(f"Database connection failed: {e}")
        return

    await render_header(state)

    with ui.row().classes('w-full justify-center px-2 pt-2'):
        with ui.tabs().classes('w-full max-w-xl justify-center') as tabs:
            ui.tab('Dashboard', label=i18n.t('dashboard'))
            ui.tab('Order', label=i18n.t('order_update'))

    with ui.tab_panels(tabs, value='Dashboard').classes('w-full'):
        with ui.tab_panel('Dashboard'):
            await render_dashboard(state)
        with ui.tab_panel('Order'):
            await render_order_tab(state)

    await render_floating_button(state)

    ui.timer(30.0, lambda: asyncio.create_task(state.refresh_all()))

    await state.refresh_all()
    logger.info("Dashboard fully rendered")

# =========================================================
# Startup
# =========================================================

if __name__ in {"__main__", "__mp_main__"}:
    logger.info(f"Starting {config.STORE_NAME} Inventory System")
    logger.info(f"Host: {config.APP_HOST}, Port: {config.APP_PORT}")
    ui.run(
        host=config.APP_HOST,
        port=config.APP_PORT,
        title=f"{config.STORE_NAME} — Inventory System",
        favicon="🛒",
        dark=False,
        reload=config.APP_RELOAD,
        show=False,
    )