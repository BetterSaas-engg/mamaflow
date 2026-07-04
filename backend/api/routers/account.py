from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.user import User
from api.services.account import delete_account

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete the authed user's account + data and revoke Gmail access."""
    await delete_account(db, user)
