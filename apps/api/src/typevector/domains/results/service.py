"""TypeVector Arena — Results Publication & Privacy-Sanitized Leaderboard Service."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.lifecycle import EventStatus
from typevector.domains.events.models import Event
from typevector.domains.identity.models import User
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.results.models import PublishedRankRow, PublishedResult
from typevector.domains.results.schemas import (
    PublicLeaderboardRow,
    PublicPublishedResultRead,
)
from typevector.domains.rounds.models import Round
from typevector.domains.scoring.aggregator import RoundScoreItem, aggregate_participant_rounds
from typevector.domains.scoring.models import ParticipantScore
from typevector.errors import ConflictError, EntityNotFoundError, InvariantViolationError


class ResultsService:
    """Domain service managing immutable published standings, amendments, and privacy masking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_event(self, event_id: uuid.UUID) -> PublishedResult:
        """Fetch current published result for an event."""
        stmt = (
            select(PublishedResult)
            .where(
                PublishedResult.event_id == event_id,
                PublishedResult.is_current.is_(True),
            )
            .options(selectinload(PublishedResult.rows))
            .order_by(PublishedResult.version_number.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        result = res.scalar_one_or_none()
        if not result:
            raise EntityNotFoundError(entity="PublishedResult", identifier=event_id)
        return result

    async def list_event_results(self, event_id: uuid.UUID) -> list[PublishedResult]:
        """Fetch all historical published versions (v1, v2, etc.) for an event."""
        stmt = (
            select(PublishedResult)
            .where(PublishedResult.event_id == event_id)
            .options(selectinload(PublishedResult.rows))
            .order_by(PublishedResult.version_number.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def preview_results(self, event_id: uuid.UUID) -> dict[str, Any]:
        """Preview server-compiled results for an event without mutating state."""
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        ranked_rows, signed_hash = await self._compile_rankings(event)

        can_publish = True
        block_reason = None
        if event.is_prize_event and event.ruleset_approval_status != "approved":
            can_publish = False
            block_reason = "Prize event scoring approval not recorded. Tournament director must approve ruleset."

        user_ids = [r["user_id"] for r in ranked_rows]
        users_map: dict[uuid.UUID, str] = {}
        if user_ids:
            users_stmt = select(User).where(User.id.in_(user_ids))
            users_res = await self.session.execute(users_stmt)
            users_map = {u.id: u.display_name for u in users_res.scalars().all()}

        rankings = []
        for idx, r in enumerate(ranked_rows, start=1):
            rankings.append(
                {
                    "user_id": r["user_id"],
                    "display_name": users_map.get(r["user_id"], "Anonymous"),
                    "rank_order": idx,
                    "gross_wpm": r["gross_wpm"],
                    "net_wpm": r["net_wpm"],
                    "accuracy_pct": r["accuracy_pct"],
                    "arena_score": r["arena_score"],
                    "tier": r["tier"],
                }
            )

        return {
            "event_id": event.id,
            "total_participants": len(rankings),
            "signed_hash": signed_hash,
            "ruleset_approval_status": event.ruleset_approval_status,
            "is_prize_event": event.is_prize_event,
            "can_publish": can_publish,
            "block_reason": block_reason,
            "rankings": rankings,
        }

    async def publish_official_results(
        self,
        event_id: uuid.UUID,
        publisher_id: uuid.UUID,
        note: str | None = None,
    ) -> PublishedResult:
        """Publish immutable Version 1 official results for an event.

        POLICY INVARIANT:
        If event is a prize competition (`is_prize_event == True`), rule approval
        must be recorded (`ruleset_approval_status == 'approved'`).
        """
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        # Policy Gate: Prize event scoring approval check
        if event.is_prize_event and event.ruleset_approval_status != "approved":
            raise InvariantViolationError(
                "Cannot publish official results for prize competition under unapproved scoring ruleset. "
                "Rule approval must be recorded by tournament director."
            )

        # Check existing publication
        existing_stmt = select(PublishedResult).where(PublishedResult.event_id == event_id)
        existing = (await self.session.execute(existing_stmt)).scalars().all()
        if existing:
            raise ConflictError(
                f"Event {event_id} already has published results. Use amendment workflow for new versions."
            )

        # Aggregate participant standings
        ranked_rows, signed_hash = await self._compile_rankings(event)

        now = datetime.now(UTC)
        published_result = PublishedResult(
            id=uuid.uuid4(),
            event_id=event_id,
            version_number=1,
            published_by_user_id=publisher_id,
            signed_hash=signed_hash,
            is_current=True,
            published_at=now,
            note=note,
            previous_version_id=None,
            amendment_reason=None,
            ruleset_approval_status=event.ruleset_approval_status,
        )
        self.session.add(published_result)
        await self.session.flush()

        for rank_idx, row in enumerate(ranked_rows, start=1):
            rank_entry = PublishedRankRow(
                id=uuid.uuid4(),
                published_result_id=published_result.id,
                rank_order=rank_idx,
                user_id=row["user_id"],
                score_id=row["score_id"],
                gross_wpm=row["gross_wpm"],
                net_wpm=row["net_wpm"],
                accuracy_pct=row["accuracy_pct"],
                arena_score=row["arena_score"],
                tier=row["tier"],
            )
            self.session.add(rank_entry)

        # Update event status to RESULTS_PUBLISHED
        event.status = EventStatus.RESULTS_PUBLISHED
        event.version = (event.version or 1) + 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=publisher_id,
            event_type="results.published_v1",
            target_type="published_result",
            target_id=str(published_result.id),
            payload_json={
                "event_id": str(event_id),
                "version": 1,
                "signed_hash": signed_hash,
                "total_rows": len(ranked_rows),
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:results_published",
            payload_json={
                "event_id": str(event_id),
                "result_id": str(published_result.id),
                "version_number": 1,
                "signed_hash": signed_hash,
                "timestamp": now.isoformat(),
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return await self.get_by_event(event_id)

    async def publish_amended_results(
        self,
        event_id: uuid.UUID,
        approver_id: uuid.UUID,
        amendment_reason: str,
    ) -> PublishedResult:
        """Publish amended results creating Version K+1 with full lineage and audit justification."""
        current_result = await self.get_by_event(event_id)
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        if not amendment_reason or not amendment_reason.strip():
            raise InvariantViolationError("Mandatory amendment rationale is required.")

        # Recompile standings post-appeal resolutions
        ranked_rows, signed_hash = await self._compile_rankings(event)

        # Mark previous version not current
        current_result.is_current = False

        now = datetime.now(UTC)
        next_ver = current_result.version_number + 1

        new_result = PublishedResult(
            id=uuid.uuid4(),
            event_id=event_id,
            version_number=next_ver,
            published_by_user_id=approver_id,
            signed_hash=signed_hash,
            is_current=True,
            published_at=now,
            note=current_result.note,
            previous_version_id=current_result.id,
            amendment_reason=amendment_reason,
            ruleset_approval_status=event.ruleset_approval_status,
        )
        self.session.add(new_result)
        await self.session.flush()

        for rank_idx, row in enumerate(ranked_rows, start=1):
            rank_entry = PublishedRankRow(
                id=uuid.uuid4(),
                published_result_id=new_result.id,
                rank_order=rank_idx,
                user_id=row["user_id"],
                score_id=row["score_id"],
                gross_wpm=row["gross_wpm"],
                net_wpm=row["net_wpm"],
                accuracy_pct=row["accuracy_pct"],
                arena_score=row["arena_score"],
                tier=row["tier"],
            )
            self.session.add(rank_entry)

        event.status = EventStatus.RESULTS_PUBLISHED
        event.version = (event.version or 1) + 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=approver_id,
            event_type="results.amended",
            target_type="published_result",
            target_id=str(new_result.id),
            payload_json={
                "event_id": str(event_id),
                "previous_version_id": str(current_result.id),
                "new_version_number": next_ver,
                "amendment_reason": amendment_reason,
                "signed_hash": signed_hash,
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:results_amended",
            payload_json={
                "event_id": str(event_id),
                "result_id": str(new_result.id),
                "version_number": next_ver,
                "signed_hash": signed_hash,
                "amendment_reason": amendment_reason,
                "timestamp": now.isoformat(),
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return await self.get_by_event(event_id)

    async def get_public_leaderboard(
        self,
        event_id: uuid.UUID,
        version_number: int | None = None,
    ) -> PublicPublishedResultRead:
        """Return public standings sanitized to eliminate all PII (Zero PII Guarantee).

        PII REDACTION:
        - Email, roll number, phone, IP address, raw keystrokes, and internal
          integrity audit notes are strictly excluded from the response schema.
        """
        stmt = (
            select(PublishedResult)
            .where(PublishedResult.event_id == event_id)
            .options(selectinload(PublishedResult.rows))
        )
        if version_number is not None:
            stmt = stmt.where(PublishedResult.version_number == version_number)
        else:
            stmt = stmt.where(PublishedResult.is_current.is_(True))

        res = await self.session.execute(stmt)
        result = res.scalar_one_or_none()
        if not result:
            raise EntityNotFoundError(
                entity="PublishedResult",
                identifier=f"event={event_id}, version={version_number or 'current'}",
            )

        public_rows: list[PublicLeaderboardRow] = []
        for r in sorted(result.rows, key=lambda x: x.rank_order):
            user = await self.session.get(User, r.user_id)
            # Mask identifier / pseudonym
            if user and hasattr(user, "display_name") and user.display_name:
                display_alias = user.display_name
            else:
                display_alias = f"TV-PARTICIPANT-{r.user_id.hex[:6].upper()}"

            public_rows.append(
                PublicLeaderboardRow(
                    rank=r.rank_order,
                    display_alias=display_alias,
                    arena_score=r.arena_score,
                    net_wpm=float(r.net_wpm),
                    accuracy_pct=float(r.accuracy_pct),
                    tier=r.tier,
                    is_eligible=r.tier != "disqualified",
                )
            )

        return PublicPublishedResultRead(
            event_id=event_id,
            version_number=result.version_number,
            published_at=result.published_at,
            is_current=result.is_current,
            is_amended=result.previous_version_id is not None,
            amendment_reason=result.amendment_reason,
            signed_hash=result.signed_hash,
            total_ranked_participants=len(public_rows),
            rankings=public_rows,
        )

    async def _compile_rankings(
        self,
        event: Event,
    ) -> tuple[list[dict[str, Any]], str]:
        """Query rounds and participant scores, executing multi-round aggregation."""
        # 1. Fetch rounds
        rounds_stmt = (
            select(Round).where(Round.event_id == event.id).order_by(Round.sequence_number.asc())
        )
        rounds = list((await self.session.execute(rounds_stmt)).scalars().all())

        # 2. Fetch all scores for this event
        scores_stmt = select(ParticipantScore).where(ParticipantScore.event_id == event.id)
        scores = list((await self.session.execute(scores_stmt)).scalars().all())

        # Group scores by user_id
        user_scores: dict[uuid.UUID, list[ParticipantScore]] = {}
        for s in scores:
            user_scores.setdefault(s.user_id, []).append(s)

        compiled: list[dict[str, Any]] = []

        for user_id, u_scores in user_scores.items():
            round_items: list[RoundScoreItem] = []
            for rnd in rounds:
                # Find score for this round
                matched_score = next((sc for sc in u_scores if sc.round_id == rnd.id), None)
                is_round_voided = rnd.status == "voided"

                if not matched_score:
                    status = "no_show"
                    score_val = 0
                    wpm_val = 0.0
                    acc_val = 0.0
                    score_id = u_scores[0].id  # reference first score
                else:
                    status = "completed" if matched_score.is_complete else "timed_out"
                    score_val = matched_score.arena_score
                    wpm_val = float(matched_score.net_wpm)
                    acc_val = float(matched_score.accuracy_pct)
                    score_id = matched_score.id

                round_items.append(
                    RoundScoreItem(
                        round_id=rnd.id,
                        sequence_number=rnd.sequence_number,
                        weight=1,  # default weight
                        is_round_voided=is_round_voided,
                        participant_status=status,
                        arena_score=score_val,
                        net_wpm=wpm_val,
                        accuracy_pct=acc_val,
                    )
                )

            agg = aggregate_participant_rounds(user_id, round_items)
            tier = "elite" if agg.aggregate_score >= 850 else "standard"
            if not agg.is_eligible:
                tier = "disqualified"

            compiled.append(
                {
                    "user_id": user_id,
                    "score_id": score_id,
                    "gross_wpm": agg.weighted_net_wpm,
                    "net_wpm": agg.weighted_net_wpm,
                    "accuracy_pct": agg.weighted_accuracy_pct,
                    "arena_score": agg.aggregate_score,
                    "tier": tier,
                }
            )

        # Sort descending by arena_score, then net_wpm, then accuracy_pct
        compiled.sort(
            key=lambda x: (x["arena_score"], x["net_wpm"], x["accuracy_pct"]),
            reverse=True,
        )

        # Compute signed digest over complete standings
        raw_manifest = json.dumps(
            [
                {
                    "u": str(c["user_id"]),
                    "s": c["arena_score"],
                    "w": c["net_wpm"],
                    "a": c["accuracy_pct"],
                }
                for c in compiled
            ],
            sort_keys=True,
        ).encode("utf-8")
        signed_hash = hashlib.sha256(raw_manifest).hexdigest()

        return compiled, signed_hash
