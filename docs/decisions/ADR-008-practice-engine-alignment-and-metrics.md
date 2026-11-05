# ADR-008: Deterministic Sequence Alignment, Educational Metrics, and Practice Engine Architecture

## Status
Accepted (2026-11-04)

## Context
TypeVector Arena requires an independent, high-craft typing practice system supporting multiple modes (common words, sentences, paragraphs, precision symbols, code snippets, speed sprint, accuracy challenge, endurance, and diagnostic).
Key engineering challenges include:
1. **Separation from Ranked Engine:** Educational practice and ranked tournament competition serve fundamentally different purposes. Ranked competition requires a strict, monotonic WebSocket stream (`arena-ws-v1`) with server-admitted keystroke sequence ACKs, writer fencing, and integer-only official scoring. Practice requires exploratory freedom, local responsiveness, character-level diff diagnostics, and pedagogical explanations.
2. **Deterministic Sequence Alignment:** Highlighting user mistakes requires aligning the target prompt against the user's typed input. A naive character-by-character index comparison fails when a single character is omitted or inserted, causing all subsequent characters to appear as cascading errors.
3. **Metric Math Transparency:** Typing platforms frequently report contradictory or vague metrics (e.g. treating backspaces inconsistently or reporting negative WPM). Every formula must have an explicit numerator, denominator, unit, and rounding policy.
4. **Layout Shift & UI Performance:** Re-rendering HTML or updating innerHTML on every keystroke causes DOM thrashing, layout recalculation, and stuttering on low-end machines.

## Decision

### 1. Decoupled Modular Monolith Practice Engine
The practice system resides entirely in `domains/practice/` (backend) and `apps/web/js/practice-engine.js` (frontend):
- Does not depend on the WebSocket ranked admission pipeline.
- Supports both authenticated participant sessions (persisted to `practice_sessions` linked to `users.id`) and anonymous sessions (`user_id = None`).
- Client displays are explicitly labeled `LOCAL PREVIEW` until an attempt completes and the server returns verified metrics and alignment diffs.

### 2. Hybrid Sequence Alignment Algorithm
To achieve deterministic, character-level alignment in $O(N)$ expected time:
- Uses `difflib.SequenceMatcher` to identify coarse equal blocks.
- Uses dynamic programming (Needleman-Wunsch with fixed scoring matrix: match = +2, substitution = -1, deletion = -1.5, insertion = -1.5) to align mismatched and substituted regions.
- Categorizes all discrepancies into deterministic error classes:
  - `match`: Expected equals actual.
  - `case_error`: Expected equals actual case-insensitively.
  - `space_error`: Space mis-typed as non-space or vice versa.
  - `punctuation_error`: Punctuation symbol mis-typed.
  - `digit_symbol_error`: Top-row number or math symbol mis-typed.
  - `substitution`: General letter replacement.
  - `omission`: Character in target skipped by user.
  - `insertion`: Extra character inserted by user.
  - `unattempted_tail`: Target characters remaining unreached when a session completes early.

### 3. Authoritative Metric Formats
- **Gross WPM:** `(total_input_chars / 5.0) / (duration_seconds / 60.0)` rounded to 2 decimal places. Standard typing convention defines 1 word as 5 keystrokes.
- **Net WPM:** `max(0.0, ((correct_chars / 5.0) - uncorrected_errors) / (duration_seconds / 60.0))` rounded to 2 decimal places. Uncorrected errors deduct 1 word (5 strokes). Clamped at 0.0 WPM.
- **Accuracy %:** `(correct_chars / total_input_chars) * 100.0` rounded to 2 decimal places.
- **Completion %:** `(attempted_chars / total_target_chars) * 100.0` rounded to 2 decimal places.

### 4. Layout-Shift Protected Client Typing Surface
- Pre-renders target text as span tokens with persistent IDs (`char-0`, `char-1`, ...).
- Keystroke events update CSS classes (`tv-char--pending`, `tv-char--correct`, `tv-char--incorrect`, `tv-char--cursor`) strictly for the active character window without tearing down or rebuilding DOM nodes.
- Fixed container line-height (`2.0`) and monospaced typography prevent line reflows.
- Hidden capture textarea handles offscreen focus, paste rejection, and IME composition events (`compositionstart`, `compositionend`).

## Consequences

### Positive
- Zero cascading error cascades: sequence alignment accurately identifies whether a character was omitted, substituted, or inserted.
- Zero layout shift and 60fps typing responsiveness without JavaScript framework overhead.
- True transparency: all metrics are explainable, backed by server evaluation and persistent JSON evidence.
- Educational diagnostics provide actionable recommendations directly tied to observed error frequencies.

### Negative / Trade-offs
- Alignment diff computation for extremely long marathon passages takes a few milliseconds of server CPU during evaluation (mitigated by coarse block decomposition).
- Client local preview metrics are approximations until verified by the server.

