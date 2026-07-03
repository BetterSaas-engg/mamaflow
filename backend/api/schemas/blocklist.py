from typing import Literal

from pydantic import BaseModel


class BlocklistResult(BaseModel):
    is_blocked: bool
    reason: str
    category: str | None
    list_status: Literal["allowed", "blocked", "unknown"]
