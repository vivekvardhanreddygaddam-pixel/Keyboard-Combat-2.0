# ADR-009: Independent Skill Tracks, Multi-Attempt Qualification, and Explainable Adaptive Recommendations

## Status
Accepted (2026-11-04)

## Context
A single global "typing level" or speed score fails to capture a typist's true capability:
1. **Masked Weaknesses:** A participant might type prose at 90 Net WPM but collapse to 25 WPM with 88% accuracy when required to type numerical brackets, currency signs, or code indentation. Aggregating these into a single metric conceals critical areas needing deliberate practice.
2. **Lucky Attempt Flukes:** Typing metrics fluctuate due to luck, short text passages, or brief bursts of speed. Advancing a user based on a single lucky attempt leads to premature level placement, frustration, and degraded learning outcomes.
3. **External Certification Misrepresentation:** Educational platforms sometimes market internal ranks (e.g., "Expert") as external professional credentials. In TypeVector Arena, level milestones must remain transparent internal learning states without claiming external accreditation.
4. **Adaptive Explainability & Sample Size:** Recommending drills without sufficient evidence or transparent explanations creates confusion and distrust. Recommendation engines must require minimum statistical sample sizes before asserting chronic finger weaknesses.

## Decision

### 1. 7 Independent Skill Tracks
We establish 7 distinct, non-conflated progression tracks:
1. `keyboard-fundamentals`: Home row anchors, finger reach independence, posture recovery.
2. `word-accuracy`: High-frequency English vocabulary, tricky digraphs, adjacent key transitions.
3. `sentence-fluency`: Punctuation timing, capitalization cadence, compound clauses.
4. `paragraph-fluency`: Sustained multi-line prose, visual buffering, mental stamina.
5. `precision-typing`: Top-row digits, currency symbols, percentages, structural brackets.
6. `code-typing`: Programming language keywords, syntax structures, indentation preservation.
7. `speed-endurance`: High-velocity rhythm, fatigue resistance, sustained speed sprints.

A user possesses an independent progression record for each track (enforced in PostgreSQL by unique constraint `uq_curriculum_user_track` on `user_curriculum_progress(user_id, skill_track_id)`).

### 2. 6-Tier Level Model & Draft Policy Designation
Each track defines 6 discrete levels:
- Level 1: Foundation
- Level 2: Beginner
- Level 3: Developing
- Level 4: Intermediate
- Level 5: Advanced
- Level 6: Expert

**Policy Notice:** All numerical thresholds (Net WPM, Accuracy %, Completion %) are versioned as `criteria_version="2026.1-draft"` and designated as `CRITERIA_STATUS="DRAFT_AWAITING_PRODUCT_APPROVAL"`. They represent configurable product policy, not external certifications.

### 3. Server-Authoritative Multi-Attempt Qualification
- Advancement requires meeting all criteria across multiple attempts (`pass_attempts_required`, typically 2 to 5 depending on level difficulty).
- Every submitted assessment is recorded in `curriculum_attempts` with `is_qualifying` boolean and full criteria checklist breakdown.
- Client-side progress is strictly a preview; level transitions occur authoritatively on the server.
- Advancing a level emits an immutable `AuditEvent` (`curriculum.level_advanced`).

### 4. Evidence-Backed Adaptive Recommendations with Sample-Size Safeguards
- The recommendation engine inspects recent practice sessions and assessment attempts.
- **Statistical Safeguard:** If sample size $N < 3$, the system returns a baseline recommendation with explicit notice: *"Insufficient sample size (N < 3). Complete at least 3 attempts to establish baseline metrics."*
- If $N \ge 3$, the system evaluates dominant error categories (digit/symbol, punctuation/case, accuracy below baseline) and suggests the specific skill track best addressing the observed weakness.
- Every recommendation outputs recorded evidence, confidence rating (`Low`, `Moderate`, `High`), and alternate track options. Users retain complete autonomy to select any track or practice mode.

## Consequences

### Positive
- Typists receive targeted, independent evaluations for prose, code, and precision typing.
- Multi-attempt requirements prevent accidental level advancement from lucky fluke runs.
- Recommendations cite transparent empirical error data rather than opaque black-box AI heuristics.
- Compliance with product truth: internal levels are clearly documented as non-certifying learning milestones.

### Negative / Trade-offs
- Users must complete multiple qualifying attempts to advance, requiring more time and deliberate practice.
- Managing 7 tracks per user slightly increases PostgreSQL row counts in `user_curriculum_progress` and `curriculum_attempts`.

