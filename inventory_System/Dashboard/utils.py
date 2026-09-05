"""Utility functions for formatting and helpers."""
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List

from Dashboard.config import config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("store")
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = setup_logging()


def format_currency(value: float, symbol: bool = True) -> str:
    if value is None:
        value = 0.0
    formatted = f"{value:,.2f}"
    return f"{config.CURRENCY_SYMBOL} {formatted}" if symbol else formatted


def format_number(value: int) -> str:
    if value is None:
        value = 0
    return f"{value:,}"


def format_date(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value
    return str(value)


def format_date_short(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime("%b %d, %Y")
        except ValueError:
            return value
    return str(value)


def records_to_dicts(records: List[Any]) -> List[Dict[str, Any]]:
    if not records:
        return []
    return [dict(r) for r in records]


def get_current_month_range() -> tuple:
    now = datetime.now()
    start = now.replace(day=1).strftime("%Y-%m-%d")
    if now.month == 12:
        end = now.replace(year=now.year + 1, month=1, day=1).strftime("%Y-%m-%d")
    else:
        end = now.replace(month=now.month + 1, day=1).strftime("%Y-%m-%d")
    return start, end


THEME_COLORS = {
    "light": {
        "bg": "#f8f9fa", "card": "#ffffff", "text": "#212529",
        "text_secondary": "#6c757d", "border": "#dee2e6",
        "primary": "#0d6efd", "success": "#198754", "warning": "#ffc107",
        "danger": "#dc3545", "info": "#0dcaf0",
        "chart_bg": "rgba(255,255,255,0.9)", "grid": "#e9ecef",
    },
    "dark": {
        "bg": "#1a1d21", "card": "#212529", "text": "#e9ecef",
        "text_secondary": "#adb5bd", "border": "#495057",
        "primary": "#6ea8fe", "success": "#75b798", "warning": "#ffda6a",
        "danger": "#ea868f", "info": "#6edff6",
        "chart_bg": "rgba(33,37,41,0.9)", "grid": "#343a40",
    }
}


def get_theme_colors(theme: str) -> Dict[str, str]:
    return THEME_COLORS.get(theme, THEME_COLORS["light"])
