import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.item import Item
from api.models.user import User
from api.schemas.item import ItemListResponse, ItemRead, ItemUpdate, item_to_read
from api.services.items import list_items

router = APIRouter(prefix="/api/v1/items", tags=["items"])


@router.get("", response_model=ItemListResponse)
async def get_items(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None, alias="to"),
    type: Literal["event", "action"] | None = Query(None),
    status: Literal["open", "done", "dismissed"] | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await list_items(
        db, user, date_from=from_, date_to=to, item_type=type, status=status
    )
    return ItemListResponse(items=[item_to_read(i) for i in items])


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: uuid.UUID,
    payload: ItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(Item, item_id)
    if item is None or item.user_id != user.id or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.status = payload.status
    await db.commit()
    await db.refresh(item)
    return item_to_read(item)
