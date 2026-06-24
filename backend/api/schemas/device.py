from typing import Literal

from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    fcm_token: str
    platform: Literal["ios", "android"]


class DeviceRead(BaseModel):
    id: str
    platform: str
