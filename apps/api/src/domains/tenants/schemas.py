import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["owner", "admin", "member"]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    created_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberOut(BaseModel):
    user_id: str
    role: Role
    # Resolved read-only from the auth schema; null if the user vanished.
    email: str | None
    name: str | None


class MemberRoleUpdate(BaseModel):
    role: Role
