"""TypeVector Arena — Curriculum Domain Service.

Coordinates educational skill tracks, multi-attempt level qualification,
authoritative assessment evaluation, and evidence-backed adaptive recommendations.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.curriculum.models import (
    CurriculumAttempt,
    SkillTrack,
    SkillTrackLevel,
    UserCurriculumProgress,
)
from typevector.domains.curriculum.schemas import CurriculumAssessmentSubmit
from typevector.domains.curriculum.tracks_catalog import (
    CRITERIA_STATUS,
    CRITERIA_VERSION,
    LEVEL_NAMES,
    TRACKS_CATALOG,
    get_track_by_slug,
    get_track_level,
    get_tracks_catalog,
)
from typevector.domains.practice.canonicalization import (
    CanonicalizationVersion,
    canonicalize_text,
)
from typevector.domains.practice.diff_engine import compute_deterministic_diff
from typevector.domains.practice.metrics import calculate_practice_metrics
from typevector.domains.practice.models import PracticeSession
from typevector.errors import EntityNotFoundError, InvariantViolationError


class CurriculumService:
    """Domain service managing curriculum tracks, levels, progression, and assessments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_tracks_seeded(self) -> None:
        """Idempotently seed the 7 skill tracks and their levels into PostgreSQL."""
        for track_data in TRACKS_CATALOG:
            stmt = select(SkillTrack).where(SkillTrack.slug == track_data["slug"])
            res = await self.session.execute(stmt)
            track = res.scalar_one_or_none()

            if not track:
                track = SkillTrack(
                    slug=track_data["slug"],
                    title=track_data["title"],
                    description=track_data["description"],
                    is_active=True,
                )
                self.session.add(track)
                await self.session.flush()

                for lvl in track_data["levels"]:
                    track_lvl = SkillTrackLevel(
                        skill_track_id=track.id,
                        level_number=lvl["level_number"],
                        title=lvl["title"],
                        min_wpm=lvl["min_wpm"],
                        min_accuracy_pct=lvl["min_accuracy_pct"],
                        pass_attempts_required=lvl["pass_attempts_required"],
                        prompt_content=lvl["prompt_content"],
                        criteria_version=CRITERIA_VERSION,
                    )
                    self.session.add(track_lvl)
                await self.session.flush()

    def list_catalog_tracks(self) -> list[dict[str, Any]]:
        """Return all 7 curriculum tracks from the catalog."""
        return get_tracks_catalog()

    def get_track_detail(self, slug: str) -> dict[str, Any] | None:
        """Fetch track and all its level criteria by slug."""
        raw_track = get_track_by_slug(slug)
        if not raw_track:
            return None
        levels = [
            {**lvl, "criteria_version": lvl.get("criteria_version", CRITERIA_VERSION)}
            for lvl in raw_track["levels"]
        ]
        return {
            **raw_track,
            "is_active": raw_track.get("is_active", True),
            "levels": levels,
        }

    async def get_user_progress_summary(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Fetch independent qualification progress for a user across all 7 tracks."""
        await self.ensure_tracks_seeded()

        # Query all existing progress rows for user
        stmt = select(UserCurriculumProgress).where(UserCurriculumProgress.user_id == user_id)
        res = await self.session.execute(stmt)
        progress_rows = {p.skill_track_id: p for p in res.scalars().all()}

        # Fetch all tracks from DB
        tracks_stmt = select(SkillTrack).where(SkillTrack.is_active.is_(True))
        tracks_res = await self.session.execute(tracks_stmt)
        all_tracks = tracks_res.scalars().all()

        summary: list[dict[str, Any]] = []
        for track in all_tracks:
            p_row = progress_rows.get(track.id)
            curr_level = p_row.current_level_number if p_row else 1
            qualifying_count = p_row.qualifying_attempts_count if p_row else 0
            last_eval = p_row.updated_at if p_row else None
            is_completed = (curr_level >= 6 and qualifying_count >= 5) or (
                p_row is not None and p_row.passed_at is not None
            )

            level_meta = get_track_level(track.slug, curr_level)
            req_attempts = level_meta["pass_attempts_required"] if level_meta else 3

            summary.append(
                {
                    "track_slug": track.slug,
                    "track_title": track.title,
                    "current_level_number": curr_level,
                    "current_level_title": LEVEL_NAMES.get(curr_level, f"Level {curr_level}"),
                    "qualifying_attempts_count": qualifying_count,
                    "pass_attempts_required": req_attempts,
                    "is_track_completed": is_completed,
                    "criteria_version": CRITERIA_VERSION,
                    "criteria_status": CRITERIA_STATUS,
                    "last_evaluated_at": last_eval,
                }
            )

        return summary

    async def evaluate_assessment(
        self, user_id: uuid.UUID, submission: CurriculumAssessmentSubmit
    ) -> dict[str, Any]:
        """Evaluate a level assessment attempt authoritatively against versioned criteria.

        Multi-attempt rule: A single lucky attempt cannot advance a user.
        Advancement occurs strictly when qualifying_attempts_count reaches pass_attempts_required.
        """
        await self.ensure_tracks_seeded()

        # 1. Validate track and level
        track_meta = get_track_by_slug(submission.track_slug)
        if not track_meta:
            raise EntityNotFoundError(entity="SkillTrack", identifier=submission.track_slug)

        level_meta = get_track_level(submission.track_slug, submission.level_number)
        if not level_meta:
            raise EntityNotFoundError(
                entity="SkillTrackLevel",
                identifier=f"{submission.track_slug}-lvl-{submission.level_number}",
            )

        # Look up track record in PostgreSQL
        track_stmt = select(SkillTrack).where(SkillTrack.slug == submission.track_slug)
        t_res = await self.session.execute(track_stmt)
        track_row = t_res.scalar_one_or_none()
        if not track_row:
            raise EntityNotFoundError(entity="SkillTrack", identifier=submission.track_slug)

        # 2. Canonicalize text
        canon_version = (
            CanonicalizationVersion.V1_CODE
            if submission.track_slug == "code-typing"
            else CanonicalizationVersion.V1_STANDARD
        )
        target_canon = canonicalize_text(level_meta["prompt_content"], version=canon_version)
        input_canon = canonicalize_text(submission.input_text, version=canon_version)

        # 3. Timing and alignment diff
        duration_seconds = max(
            0.5,
            (submission.completed_at - submission.started_at).total_seconds(),
        )
        diff_result = compute_deterministic_diff(target_canon, input_canon)
        metrics = calculate_practice_metrics(diff_result, duration_seconds)

        # 4. Evaluate against criteria dimensions
        min_wpm_required = float(level_meta["min_wpm"])
        min_acc_required = float(level_meta["min_accuracy_pct"])
        completion_req = 99.0  # Must complete full prompt (within 1% tolerance)

        actual_wpm = float(metrics["net_wpm"])
        actual_acc = float(metrics["accuracy_pct"])
        actual_comp = float(metrics["completion_pct"])

        wpm_passed = actual_wpm >= min_wpm_required
        acc_passed = actual_acc >= min_acc_required
        comp_passed = actual_comp >= completion_req

        is_qualifying = wpm_passed and acc_passed and comp_passed

        # Criteria checklist for transparent UI explanation
        criteria_checklist = [
            {
                "name": "Net WPM Velocity",
                "required": min_wpm_required,
                "actual": actual_wpm,
                "unit": "WPM",
                "passed": wpm_passed,
            },
            {
                "name": "Accuracy Precision",
                "required": min_acc_required,
                "actual": actual_acc,
                "unit": "%",
                "passed": acc_passed,
            },
            {
                "name": "Full Completion",
                "required": completion_req,
                "actual": actual_comp,
                "unit": "%",
                "passed": comp_passed,
            },
        ]

        # 5. Fetch or initialize UserCurriculumProgress
        prog_stmt = select(UserCurriculumProgress).where(
            UserCurriculumProgress.user_id == user_id,
            UserCurriculumProgress.skill_track_id == track_row.id,
        )
        p_res = await self.session.execute(prog_stmt)
        progress = p_res.scalar_one_or_none()

        if not progress:
            progress = UserCurriculumProgress(
                user_id=user_id,
                skill_track_id=track_row.id,
                current_level_number=1,
                qualifying_attempts_count=0,
                total_attempts=0,
                criteria_version=CRITERIA_VERSION,
            )
            self.session.add(progress)
            await self.session.flush()

        # Check if submission matches user's current track level
        if submission.level_number > progress.current_level_number:
            raise InvariantViolationError(
                f"Cannot attempt Level {submission.level_number}; current level is {progress.current_level_number}."
            )

        # 6. Record Attempt Audit
        evaluation_details = {
            "track_slug": submission.track_slug,
            "level_number": submission.level_number,
            "criteria_version": CRITERIA_VERSION,
            "metrics": metrics,
            "criteria_checklist": criteria_checklist,
            "is_qualifying": is_qualifying,
        }

        attempt_record = CurriculumAttempt(
            user_id=user_id,
            skill_track_id=track_row.id,
            level_number=submission.level_number,
            net_wpm=actual_wpm,
            accuracy_pct=actual_acc,
            completion_pct=actual_comp,
            is_qualifying=is_qualifying,
            criteria_version=CRITERIA_VERSION,
            evaluation_details_json=evaluation_details,
        )
        self.session.add(attempt_record)

        # 7. Update progress state
        progress.total_attempts += 1
        did_advance = False
        old_level = progress.current_level_number
        pass_required = level_meta["pass_attempts_required"]

        if is_qualifying and submission.level_number == progress.current_level_number:
            progress.qualifying_attempts_count += 1

            if progress.qualifying_attempts_count >= pass_required:
                if progress.current_level_number < 6:
                    progress.current_level_number += 1
                    progress.qualifying_attempts_count = 0
                    did_advance = True
                else:
                    progress.passed_at = datetime.now(UTC)

                # Emit audit event
                audit = AuditEvent(
                    actor_user_id=user_id,
                    event_type="curriculum.level_advanced",
                    target_type="user_curriculum_progress",
                    target_id=str(progress.id),
                    payload_json={
                        "track_slug": submission.track_slug,
                        "old_level": old_level,
                        "new_level": progress.current_level_number,
                        "criteria_version": CRITERIA_VERSION,
                    },
                )
                self.session.add(audit)

        await self.session.flush()

        # 8. Synthesize transparent plain-language explanation
        level_title = level_meta["title"]
        if is_qualifying:
            if did_advance:
                explanation = (
                    f"Mastery confirmed! You completed {pass_required}/{pass_required} qualifying attempts. "
                    f"Advanced from Level {old_level} ({LEVEL_NAMES.get(old_level)}) to Level {progress.current_level_number} ({LEVEL_NAMES.get(progress.current_level_number)})."
                )
            else:
                remaining = pass_required - progress.qualifying_attempts_count
                explanation = (
                    f"Qualifying attempt recorded ({progress.qualifying_attempts_count}/{pass_required}). "
                    f"Need {remaining} more qualifying attempt(s) meeting all criteria to advance."
                )
        else:
            reasons = []
            if not wpm_passed:
                reasons.append(f"Net WPM {actual_wpm} was below required {min_wpm_required}")
            if not acc_passed:
                reasons.append(f"Accuracy {actual_acc}% was below required {min_acc_required}%")
            if not comp_passed:
                reasons.append(f"Completion {actual_comp}% was incomplete")
            explanation = f"Attempt did not qualify: {'; '.join(reasons)}. Keep practicing to achieve consistent precision."

        return {
            "track_slug": submission.track_slug,
            "level_number": submission.level_number,
            "level_title": level_title,
            "net_wpm": actual_wpm,
            "accuracy_pct": actual_acc,
            "completion_pct": actual_comp,
            "is_qualifying": is_qualifying,
            "qualifying_attempts_completed": progress.qualifying_attempts_count,
            "pass_attempts_required": pass_required,
            "did_advance_level": did_advance,
            "new_level_number": progress.current_level_number,
            "criteria_version": CRITERIA_VERSION,
            "criteria_status": CRITERIA_STATUS,
            "criteria_checklist": criteria_checklist,
            "explanation": explanation,
        }

    async def get_adaptive_recommendation(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Generate evidence-backed adaptive recommendations based on observed weaknesses.

        Statistical Safeguard: Requires at least 3 completed attempts before diagnosing
        specific finger weaknesses. Recommends deliberate practice based on actual recorded error breakdown.
        """
        # Query recent practice sessions for user
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.desc())
            .limit(10)
        )
        res = await self.session.execute(stmt)
        sessions = res.scalars().all()
        sample_size = len(sessions)

        alternative_tracks = [
            "keyboard-fundamentals",
            "word-accuracy",
            "sentence-fluency",
            "code-typing",
        ]

        if sample_size < 3:
            return {
                "recommended_track_slug": "keyboard-fundamentals",
                "recommended_track_title": "Keyboard Fundamentals",
                "recommended_level": 1,
                "reason": "Baseline calibration: Insufficient sample size to detect specific finger reach biases.",
                "evidence": f"Recorded attempts: {sample_size} (Minimum N=3 required for statistical confidence).",
                "confidence": f"Low (sample size N={sample_size})",
                "sample_size": sample_size,
                "alternative_track_slugs": alternative_tracks,
            }

        # Aggregate error breakdown across recent attempts
        total_errors: dict[str, int] = {
            "case_error": 0,
            "space_error": 0,
            "punctuation_error": 0,
            "digit_symbol_error": 0,
            "substitution": 0,
            "omission": 0,
            "insertion": 0,
        }
        total_net_wpm = 0.0
        total_acc = 0.0

        for s in sessions:
            evidence = s.error_diff_json or {}
            breakdown = evidence.get("error_breakdown", {})
            for k in total_errors:
                total_errors[k] += breakdown.get(k, 0)
            total_net_wpm += float(s.net_wpm or 0.0)
            total_acc += float(s.accuracy_pct or 100.0)

        avg_wpm = round(total_net_wpm / sample_size, 1)
        avg_acc = round(total_acc / sample_size, 1)
        sum_errors = max(1, sum(total_errors.values()))

        # Determine dominant weakness
        sym_ratio = total_errors["digit_symbol_error"] / sum_errors
        punct_ratio = total_errors["punctuation_error"] / sum_errors
        case_ratio = total_errors["case_error"] / sum_errors

        confidence = "High" if sample_size >= 6 else "Moderate"

        if sym_ratio >= 0.20:
            return {
                "recommended_track_slug": "precision-typing",
                "recommended_track_title": "Precision Typing",
                "recommended_level": 2,
                "reason": "Top-row symbol reaches: Digit and symbol mistakes represent a disproportionate share of errors.",
                "evidence": f"Symbol errors accounted for {round(sym_ratio * 100, 1)}% of mistakes across {sample_size} attempts.",
                "confidence": f"{confidence} (sample size N={sample_size})",
                "sample_size": sample_size,
                "alternative_track_slugs": alternative_tracks,
            }

        if punct_ratio >= 0.25 or case_ratio >= 0.25:
            return {
                "recommended_track_slug": "sentence-fluency",
                "recommended_track_title": "Sentence Fluency",
                "recommended_level": 2,
                "reason": "Punctuation & shift key coordination: Capitalization and commas show elevated error rates.",
                "evidence": f"Punctuation & case errors accounted for {round((punct_ratio + case_ratio) * 100, 1)}% of mistakes across {sample_size} attempts.",
                "confidence": f"{confidence} (sample size N={sample_size})",
                "sample_size": sample_size,
                "alternative_track_slugs": alternative_tracks,
            }

        if avg_acc < 95.0:
            return {
                "recommended_track_slug": "word-accuracy",
                "recommended_track_title": "Word Accuracy",
                "recommended_level": 2,
                "reason": "Precision over velocity: Average accuracy is below the 95% baseline.",
                "evidence": f"Average accuracy across {sample_size} attempts is {avg_acc}% at {avg_wpm} Net WPM.",
                "confidence": f"{confidence} (sample size N={sample_size})",
                "sample_size": sample_size,
                "alternative_track_slugs": alternative_tracks,
            }

        # Balanced profile: recommend advancing speed & endurance or code typing
        return {
            "recommended_track_slug": "speed-endurance",
            "recommended_track_title": "Speed & Endurance",
            "recommended_level": 3,
            "reason": "High precision baseline: Strong accuracy across core vocabulary indicates readiness for stamina drills.",
            "evidence": f"Maintained {avg_acc}% average accuracy at {avg_wpm} Net WPM across {sample_size} attempts.",
            "confidence": f"{confidence} (sample size N={sample_size})",
            "sample_size": sample_size,
            "alternative_track_slugs": alternative_tracks,
        }
