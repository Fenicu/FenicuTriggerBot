import logging
from datetime import date, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import engine
from app.db.models.reputation_log import ReputationLog

logger = logging.getLogger(__name__)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def cleanup_old_logs() -> None:
    """Удалить записи reputation_logs старше 2 дней."""
    cutoff = date.today() - timedelta(days=2)

    async with async_session() as session:
        stmt = delete(ReputationLog).where(ReputationLog.date < cutoff)
        result = await session.execute(stmt)
        await session.commit()

        logger.info(f"Cleaned up {result.rowcount} old reputation logs")
