"""Entry point for python -m Dashboard"""
from nicegui import ui

# Import app module to register the @ui.page('/') handler
import Dashboard.app

from Dashboard.config import config
from Dashboard.utils import logger

if __name__ == "__main__":
    logger.info(f"Starting {config.STORE_NAME} Inventory System")
    ui.run(
        host=config.APP_HOST,
        port=config.APP_PORT,
        title=f"{config.STORE_NAME} — Inventory System",
        favicon="🛒",
        dark=False,
        reload=config.APP_RELOAD,
        show=False,
    )
