from fastapi import APIRouter
from pydantic import BaseModel

from src.core.auth import CurrentUser

router = APIRouter(tags=["users"])


class MeResponse(BaseModel):
    user_id: str
    email: str | None


@router.get("/me")
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(user_id=user.user_id, email=user.email)
