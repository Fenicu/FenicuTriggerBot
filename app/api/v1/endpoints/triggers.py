import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.db.models.user import User
from app.services.trigger_service import delete_trigger_by_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict[str, str]:
    """Удалить триггер."""
    success = await delete_trigger_by_id(session, trigger_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"status": "ok"}
