import logging

from app.services.gban_service import GbanService

logger = logging.getLogger(__name__)


async def update_gban_task() -> None:
    """Задача для обновления глобального бан-листа."""
    logger.info("Starting Global Banlist Updater...")
    try:
        await GbanService.update_banlist()
    except Exception as e:
        logger.error(f"Error in update_gban_task: {e}")
