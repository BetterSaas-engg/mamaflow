from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.user import User
from api.schemas.device import DeviceRead, DeviceRegisterRequest, DeviceUnregisterRequest
from api.services.devices import register_device, unregister_device

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRead)
async def register(
    payload: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await register_device(db, user, payload.fcm_token, payload.platform)
    return DeviceRead(id=str(device.id), platform=device.platform)


@router.post("/unregister", status_code=204)
async def unregister(
    payload: DeviceUnregisterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await unregister_device(db, user, payload.fcm_token)
    return Response(status_code=204)
