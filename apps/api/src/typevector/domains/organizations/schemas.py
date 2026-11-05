"""TypeVector Arena — Organizations Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationRead(BaseModel):
    """Organization public profile."""

    id: uuid.UUID
    slug: str
    name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    """Organization creation payload."""

    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=255)


class OrganizationMemberRead(BaseModel):
    """Organization membership representation."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationMemberAdd(BaseModel):
    """Payload to add a user to an organization."""

    user_id: uuid.UUID
    role: str = Field(pattern=r"^(owner|organizer|reviewer|member)$")


class OrganizationMemberDetailRead(BaseModel):
    """Organization membership with user profile information."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    email: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
