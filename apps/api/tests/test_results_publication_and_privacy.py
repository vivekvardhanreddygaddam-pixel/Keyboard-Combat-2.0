"""TypeVector Arena — Results Publication, Immutability, Amendments, and Privacy Tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.models import Event
from typevector.domains.identity.models import User
from typevector.domains.results.models import PublishedRankRow, PublishedResult
from typevector.domains.results.service import ResultsService
from typevector.domains.rounds.models import Round
from typevector.domains.scoring.models import ParticipantScore
from typevector.errors import ConflictError, InvariantViolationError


class MockResultsSession:
    """Mock async session tracking events, rounds, scores, users, and published results."""

    def __init__(self) -> None:
        self.events: dict[uuid.UUID, Event] = {}
        self.rounds: dict[uuid.UUID, list[Round]] = {}
        self.scores: dict[uuid.UUID, list[ParticipantScore]] = {}
        self.users: dict[uuid.UUID, User] = {}
        self.results: dict[uuid.UUID, list[PublishedResult]] = {}
        self.rank_rows: dict[uuid.UUID, list[PublishedRankRow]] = {}
        self.added: list[object] = []

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is Event:
            return self.events.get(identifier)
        if model is User:
            return self.users.get(identifier)
        if model is PublishedResult:
            for res_list in self.results.values():
                for r in res_list:
                    if r.id == identifier:
                        return r
        return None

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        # PublishedResult query
        if "published_results" in stmt_str:

            def scalar_one_or_none() -> object | None:
                for _eid, res_list in self.results.items():
                    for r in res_list:
                        if r.is_current:
                            return r
                return None

            def scalars_all() -> list[PublishedResult]:
                all_res: list[PublishedResult] = []
                for res_list in self.results.values():
                    all_res.extend(res_list)
                return all_res

            mock_result.scalar_one_or_none = scalar_one_or_none
            mock_result.scalars.return_value.all = scalars_all
            return mock_result

        # Rounds query
        if "from rounds" in stmt_str:
            for _eid, rnd_list in self.rounds.items():
                mock_result.scalars.return_value.all.return_value = rnd_list
                return mock_result
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        # Scores query
        if "participant_scores" in stmt_str:
            for _eid, sc_list in self.scores.items():
                mock_result.scalars.return_value.all.return_value = sc_list
                return mock_result
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, Event):
            self.events[instance.id] = instance
        elif isinstance(instance, Round):
            self.rounds.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, ParticipantScore):
            self.scores.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, User):
            self.users[instance.id] = instance
        elif isinstance(instance, PublishedResult):
            self.results.setdefault(instance.event_id, []).append(instance)
        elif isinstance(instance, PublishedRankRow):
            self.rank_rows.setdefault(instance.published_result_id, []).append(instance)
            # Link to published result
            for res_list in self.results.values():
                for res in res_list:
                    if res.id == instance.published_result_id and instance not in res.rows:
                        res.rows.append(instance)

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_prize_event_unapproved_ruleset_blocked() -> None:
    """POLICY GATE: Prize event cannot publish official results under unapproved ruleset."""
    session = MockResultsSession()
    service = ResultsService(session)

    event_id = uuid.uuid4()
    publisher_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="prize-cup",
        title="Prize Cup $10k",
        status="review",
        is_prize_event=True,  # Prize competition!
        ruleset_approval_status="draft_awaiting_approval",  # Unapproved!
    )
    session.add(event)

    with pytest.raises(InvariantViolationError) as exc:
        await service.publish_official_results(
            event_id=event_id,
            publisher_id=publisher_id,
            note="Publishing unapproved prize event",
        )
    assert (
        "Cannot publish official results for prize competition under unapproved scoring ruleset"
        in str(exc.value)
    )


@pytest.mark.asyncio
async def test_publish_official_results_and_immutable_amendment_lineage() -> None:
    """Verify Version 1 publication, double-publish prevention, and Version 2 amendment lineage."""
    session = MockResultsSession()
    service = ResultsService(session)

    event_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    event = Event(
        id=event_id,
        organization_id=uuid.uuid4(),
        slug="sprint-championship",
        title="Sprint Championship",
        status="review",
        is_prize_event=False,
        ruleset_approval_status="approved",
    )
    session.add(event)

    round_obj = Round(id=uuid.uuid4(), event_id=event_id, sequence_number=1, status="completed")
    session.add(round_obj)

    score1 = ParticipantScore(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        event_id=event_id,
        round_id=round_obj.id,
        user_id=user1_id,
        gross_wpm=100.0,
        net_wpm=95.0,
        accuracy_pct=98.0,
        arena_score=890,
        is_complete=True,
        canonical_hash="hash1",
        score_status="provisional",
    )
    session.add(score1)

    score2 = ParticipantScore(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        event_id=event_id,
        round_id=round_obj.id,
        user_id=user2_id,
        gross_wpm=80.0,
        net_wpm=75.0,
        accuracy_pct=95.0,
        arena_score=850,
        is_complete=True,
        canonical_hash="hash2",
        score_status="provisional",
    )
    session.add(score2)

    # 1. Publish Version 1
    v1 = await service.publish_official_results(
        event_id=event_id,
        publisher_id=admin_id,
        note="Initial official publication",
    )
    assert v1.version_number == 1
    assert v1.is_current is True
    assert v1.previous_version_id is None
    assert event.status == "results_published"

    # 2. Attempting to call publish_official_results again on same event is BLOCKED
    with pytest.raises(ConflictError) as exc:
        await service.publish_official_results(
            event_id=event_id,
            publisher_id=admin_id,
            note="Duplicate publish",
        )
    assert "already has published results. Use amendment workflow" in str(exc.value)

    # 3. Publish Version 2 Amendment
    v2 = await service.publish_amended_results(
        event_id=event_id,
        approver_id=admin_id,
        amendment_reason="Appeal #402 upheld regarding rapid-trigger keyboard latency.",
    )
    assert v2.version_number == 2
    assert v2.is_current is True
    assert v2.previous_version_id == v1.id
    assert v1.is_current is False
    assert v2.amendment_reason == "Appeal #402 upheld regarding rapid-trigger keyboard latency."


@pytest.mark.asyncio
async def test_public_leaderboard_zero_pii_sanitization() -> None:
    """Verify that public leaderboard response strictly sanitizes all participant PII."""
    session = MockResultsSession()
    service = ResultsService(session)

    event_id = uuid.uuid4()
    participant_id = uuid.uuid4()

    # User with private institutional data
    user = User(
        id=participant_id,
        email="student.secret@university.edu",
        display_name="SpeedDemon99",
        role="participant",
        status="active",
    )
    session.add(user)

    result = PublishedResult(
        id=uuid.uuid4(),
        event_id=event_id,
        version_number=1,
        published_by_user_id=uuid.uuid4(),
        signed_hash="signed123",
        is_current=True,
        published_at=datetime.now(UTC),
        ruleset_approval_status="approved",
    )
    session.add(result)

    rank_row = PublishedRankRow(
        id=uuid.uuid4(),
        published_result_id=result.id,
        rank_order=1,
        user_id=participant_id,
        score_id=uuid.uuid4(),
        gross_wpm=110.0,
        net_wpm=105.0,
        accuracy_pct=99.0,
        arena_score=910,
        tier="elite",
    )
    session.add(rank_row)

    public_board = await service.get_public_leaderboard(event_id)
    assert public_board.total_ranked_participants == 1
    row = public_board.rankings[0]

    # Alias is exposed, NEVER real email or internal IDs!
    assert row.display_alias == "SpeedDemon99"
    assert row.arena_score == 910
    assert row.net_wpm == 105.0

    # Verify that raw PII does NOT exist on the schema object
    assert not hasattr(row, "email")
    assert not hasattr(row, "phone")
    assert not hasattr(row, "roll_number")
    assert not hasattr(row, "ip_address")
    assert not hasattr(row, "raw_keystrokes")
