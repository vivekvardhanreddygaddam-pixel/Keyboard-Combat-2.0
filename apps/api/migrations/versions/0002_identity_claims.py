"""Identity claims and verification workflow schema.

Revision ID: 0002_identity_claims
Revises: 0001_initial_schema
Create Date: 2026-11-04 00:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_identity_claims"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "identity_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_type", sa.String(50), nullable=False),
        sa.Column("claim_value", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), server_default="unverified", nullable=False),
        sa.Column("verification_method", sa.String(50), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_claims_user_id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_claims_org_id"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], name="fk_claims_reviewer_id"),
        sa.UniqueConstraint("organization_id", "claim_type", "claim_value", name="uq_claims_org_type_val"),
    )
    op.create_index("ix_identity_claims_user_id", "identity_claims", ["user_id"])
    op.create_index("ix_identity_claims_organization_id", "identity_claims", ["organization_id"])
    op.create_index("ix_identity_claims_status", "identity_claims", ["status"])


def downgrade() -> None:
    op.drop_table("identity_claims")

