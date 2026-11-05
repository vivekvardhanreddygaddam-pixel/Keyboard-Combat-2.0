"""TypeVector Arena — Central Model Registry.

All declarative models are imported here to guarantee that Base.metadata
contains the complete schema for Alembic migrations and database operations.
"""

from typevector.db.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    OptimisticLockMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from typevector.domains.audit.models import AuditEvent
from typevector.domains.curriculum.models import (
    CurriculumAttempt,
    SkillTrack,
    SkillTrackLevel,
    UserCurriculumProgress,
)
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.exports.models import ExportJob
from typevector.domains.identity.models import IdentityClaim, User, UserCredential, UserSession
from typevector.domains.integrity_review.models import IntegrityAppeal, IntegrityCase
from typevector.domains.notifications.models import (
    NotificationDelivery,
    TransactionalOutbox,
)
from typevector.domains.operations.models import RetentionJob
from typevector.domains.organizations.models import Organization, OrganizationMember
from typevector.domains.practice.models import PracticeSession
from typevector.domains.ranked_input.models import RankedAttempt, RankedInputBatch
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.results.models import PublishedRankRow, PublishedResult
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.domains.scoring.models import ParticipantScore

__all__ = [
    "POSTGRES_NAMING_CONVENTION",
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "OptimisticLockMixin",
    "User",
    "UserCredential",
    "UserSession",
    "IdentityClaim",
    "Organization",
    "OrganizationMember",
    "Event",
    "EventRuleset",
    "EventRegistration",
    "Round",
    "ChallengePrompt",
    "RankedAttempt",
    "RankedInputBatch",
    "ParticipantScore",
    "PracticeSession",
    "SkillTrack",
    "SkillTrackLevel",
    "CurriculumAttempt",
    "UserCurriculumProgress",
    "PublishedResult",
    "PublishedRankRow",
    "IntegrityCase",
    "IntegrityAppeal",
    "TransactionalOutbox",
    "NotificationDelivery",
    "ExportJob",
    "AuditEvent",
    "RetentionJob",
]
