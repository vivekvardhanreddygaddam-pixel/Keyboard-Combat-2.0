"""TypeVector Arena — Integrity Review and Appeals Schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntegrityAppealRead(BaseModel):
    """Integrity appeal response schema."""

    id: uuid.UUID
    integrity_case_id: uuid.UUID
    user_id: uuid.UUID
    appeal_statement: str
    status: str
    reviewed_by_user_id: uuid.UUID | None = None
    review_notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrityCaseRead(BaseModel):
    """Integrity case summary schema."""

    id: uuid.UUID
    event_id: uuid.UUID
    round_id: uuid.UUID
    attempt_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    flag_reasons_json: dict[str, Any]
    evidence_references_json: dict[str, Any]
    assigned_reviewer_id: uuid.UUID | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    second_reviewer_id: uuid.UUID | None = None
    second_approved_at: datetime | None = None
    second_approval_notes: str | None = None
    created_at: datetime
    appeals: list[IntegrityAppealRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CaseResolutionRequest(BaseModel):
    """Primary judge case resolution payload."""

    decision: str = Field(
        ..., pattern=r"^(upheld|dismissed)$", description="'upheld' or 'dismissed'"
    )
    rationale: str = Field(
        ..., min_length=5, max_length=1000, description="Mandatory judging rationale"
    )
    evidence_references: dict[str, Any] = Field(
        default_factory=dict, description="References to telemetry hashes or logs"
    )


class SecondApprovalRequest(BaseModel):
    """Secondary judge confirmation payload for high-impact decisions."""

    approval_decision: str = Field(
        ..., pattern=r"^(approved|rejected)$", description="'approved' or 'rejected'"
    )
    second_notes: str = Field(
        ..., min_length=5, max_length=1000, description="Mandatory second reviewer audit notes"
    )


class AppealSubmissionRequest(BaseModel):
    """Participant appeal payload."""

    appeal_statement: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Detailed statement explaining appeal grounds",
    )


class AppealDecisionRequest(BaseModel):
    """Independent appellate judge decision payload."""

    decision: str = Field(
        ..., pattern=r"^(accepted|rejected)$", description="'accepted' or 'rejected'"
    )
    review_notes: str = Field(
        ..., min_length=5, max_length=1000, description="Formal appellate decision rationale"
    )
