import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

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


InvitableRole = Literal["admin", "member"]


class InvitationCreate(BaseModel):
    email: EmailStr
    role: InvitableRole = "member"


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    invited_by: str
    expires_at: datetime
    created_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class AcceptedInvitationOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Role
