# ADR-012: Official Scoring Engine, Deterministic Replay, Integrity Review Dual-Approval, and Immutable Published Results

**Status:** Accepted  
**Date:** 2026-11-04  
**Deciders:** Principal Product Architect & Technical Lead  
**Consulted:** Engineering Team, Tournament Directors, Integrity Reviewers, Competition Organizers  
**Informed:** Platform Operators, UI/UX Engineers, Participant Community  

---

## Context & Problem Statement

Competitive typing tournaments have historically suffered from critical vulnerabilities and trust failures:
1. **Client-Authoritative Scoring:** Relying on client-reported speed (WPM) or accuracy creates trivial avenues for automated tampering, memory hacking, or script injection.
2. **UTF-8 Byte Counting Flaws:** Measuring typing speed or length by UTF-8 bytes instead of Unicode grapheme clusters or scalar values severely distorts metrics for non-ASCII scripts, accented characters, and emojis (e.g. counting a 4-byte grapheme as 4 typing units).
3. **Dropout Exploits (Gaming WPM):** Participants typing a few easy words at extreme speed (e.g. 180 WPM) and abandoning the attempt before difficult text appears, artificially inflating standings when scoring lacks completion gating.
4. **Unvetted Scoring Rules in Prize Events:** Deploying experimental, untested, or unapproved scoring algorithms in sanctioned prize competitions undermines legal and competitive legitimacy.
5. **Silent Database Updates & Mutable Results:** Overwriting published leaderboard rankings in-place destroys auditability and creates suspicion of administrative favoritism.
6. **Single-Reviewer Bias in Disqualifications:** Allowing a single administrator to unilaterally disqualify participants without dual-approval or evidence trails introduces arbitrary enforcement risks.
7. **Appellate Conflicts of Interest:** Allowing the original reviewer to hear their own appeal denies participants due process.
8. **Institutional PII Leaks on Public Leaderboards:** Exposing internal student IDs, roll numbers, personal emails, or participant IP addresses on public result pages violates privacy standards (GDPR, FERPA) and participant safety.

---

## Decision Drivers

1. **Zero Browser Authority:** The server alone computes official scores strictly from admitted append-only input evidence and pinned challenge prompt text.
2. **Pinned Canonicalization Standards:**
   - **Paragraph / Prose:** Unicode Extended Grapheme Cluster segmentation (UAX #29) with NFC challenge normalization at publication (`unicode-paragraph-v1`).
   - **Code:** Unicode scalar semantics with CRLF/CR normalized once to LF at ingestion, strictly preserving indentation, tabs, whitespace, and punctuation (`unicode-scalar-v1`).
   - Raw UTF-8 bytes must **never** be counted as typing units.
3. **Hard Completion Gate:** Under `arena-score-v1`, incomplete attempts are strictly capped at $\le 699$, while exact completed attempts are strictly bounded $\ge 700$. High speed on an abandoned attempt can never outrank a completed submission.
4. **Bitwise Replay Manifest:** Every score record stores a deterministic replay manifest hashing scorer version, canonicalizer version, challenge digest, input evidence digest, and active duration. Replay validation executes a bitwise comparison.
5. **Policy Gate for Prize Tournaments:** Scoring formula `arena-score-v1` defaults to `DRAFT_AWAITING_TOURNAMENT_APPROVAL`. Rehearsals and friendly events may evaluate scores, but official publication for prize events (`is_prize_event == True`) is strictly blocked unless `ruleset_approval_status == 'approved'`.
6. **Multi-Round Aggregation with Denominator Exclusion:** Round weights are frozen integers. When a round is voided due to platform disruption, it is excluded from both numerator and denominator of the composite aggregate score.
7. **Integrity Review Dual-Approval & Reviewer Separation:** Disqualifications and upheld integrity cases require dual approval by two distinct reviewers (`second_reviewer_id != assigned_reviewer_id`).
8. **Independent Appellate Separation:** Participant appeals must be decided by an appellate reviewer independent from both trial reviewers ($\text{appellate\_id} \notin \{\text{assigned\_id}, \text{second\_reviewer\_id}\}$).
9. **Append-Only Immutable Standings:** Version 1 of published results is immutable. Amendments append Version $K+1$ explicitly recording `previous_version_id`, reason, approver, and timestamp.
10. **Zero PII Leakage:** Public leaderboard and result views display strictly masked handles or anonymous participant identifiers; zero institutional emails, roll numbers, or IP addresses are emitted.

---

## Architectural & Lifecycle Specifications

### 1. Pinned Canonicalization Engine

```
[Inbound Prompt / Submission]
            │
    ┌───────┴───────┐
    ▼               ▼
(Paragraph/Prose) (Code Typing)
    │               │
  NFC Normalization CRLF/CR -> LF Normalization
    │               │
UAX #29 Grapheme    Unicode Scalar
Clusters            Semantics (Exact Whitespace)
    │               │
    └───────┬───────┘
            ▼
[Canonical Typing Units List + SHA-256 Digest]
```

Canonicalization is version-pinned. For grapheme segmentation, standard grapheme cluster boundaries are identified:
- Regional indicators and emoji sequences (e.g. flag sequences, family emoji $\approx 25$ bytes) segment into 1 canonical typing unit.
- Multi-byte scripts (e.g. Japanese kanji/hiragana $\approx 3$ bytes each) segment into 1 canonical unit per character.
- Combining diacritical marks (e.g. `e` + `\u0301`) segment into 1 grapheme cluster after NFC normalization.

### 2. The `arena-score-v1` Formula & Completion Gating

Let:
- $N$: Canonical total challenge units ($N > 0$).
- $M$: Matched canonical units typed correctly in prefix order ($0 \le M \le N$).
- $D$: Active elapsed duration in seconds ($D > 0$).
- $E$: Incurred error penalties (uncorrected errors and excess keystrokes).
- $C = \frac{M}{N}$: Completion ratio ($0.0 \le C \le 1.0$).
- $W_{\text{net}} = \max\left(0.0, \frac{(M - E) / 5}{D / 60}\right)$: Net typing speed in WPM.
- $A = \frac{M}{M + E} \cdot 100$: Accuracy percentage ($0.0 \le A \le 100.0$).

The score computation is partitioned into two mutually exclusive regimes:

$$\text{ArenaScore}(M, N, D, E) = \begin{cases} 
\min\left(699, \lfloor C \times 500 + W_{\text{net}} \times 1.5 + A \times 0.5 \rfloor\right) & \text{if } M < N \text{ (Incomplete)} \\
\min\left(1000, \max\left(700, \lfloor 700 + W_{\text{net}} \times 2.0 + (A - 90.0) \times 10 \rfloor\right)\right) & \text{if } M = N \text{ (Completed)}
\end{cases}$$

Guards:
- If $N \le 0$ or $D \le 0$, the scorer returns score $0$.
- Incomplete attempts can never score $\ge 700$, regardless of net WPM.
- Exact completed attempts can never score $< 700$, guaranteeing that completion always outranks abandonment.

### 3. Policy Gate for Prize Tournaments

To prevent unvetted or modified scoring rules from affecting monetary or sanctioned competitions:
- The scoring specification is versioned (`arena-score-v1`).
- Events track `ruleset_approval_status: str` (default `draft_awaiting_approval`) and `is_prize_event: bool`.
- Rehearsals, friendly matches, and internal testing can compute scores under `draft_awaiting_approval`.
- In `publish_official_results(event_id)`:
  ```python
  if event.is_prize_event and event.ruleset_approval_status != "approved":
      raise InvariantViolationError(
          "Cannot publish official results for prize competition under unapproved scoring ruleset."
      )
  ```

### 4. Multi-Round Aggregation & Void Handling

In a multi-round competition with rounds $r \in \mathcal{R}$, each round has a frozen integer weight $w_r > 0$.
If round $v$ is voided due to platform degradation, hardware malfunction, or organizer cancellation, it is added to the set of voided rounds $\mathcal{V} \subset \mathcal{R}$.

The composite aggregate score is:

$$S_{\text{composite}} = \begin{cases}
0.0 & \text{if } \sum_{r \notin \mathcal{V}} w_r = 0 \\
\frac{\sum_{r \notin \mathcal{V}} w_r \cdot s_r}{\sum_{r \notin \mathcal{V}} w_r} & \text{otherwise}
\end{cases}$$

Voided rounds are completely excluded from both numerator and denominator, preventing participants from being penalized for canceled rounds.

### 5. Integrity Review Dual-Approval & Appellate Separation

```mermaid
sequenceDiagram
    autonumber
    actor System as Anti-Cheat / Anomaly Flag
    actor R1 as Primary Reviewer
    actor R2 as Secondary Reviewer
    actor Participant as Participant
    actor Appellate as Appellate Judge

    System->>R1: Creates IntegrityCase (Flagged)
    R1->>R1: Investigates Evidence References
    alt Decision: Upheld / Disqualification
        R1->>R2: Resolves as PENDING_SECOND_APPROVAL
        Note over R2: R2 must NOT equal R1
        R2->>R2: Reviews Evidence Independently
        R2-->>System: Confirms UPHELD (Disqualification Finalized)
    else Decision: Dismissed
        R1-->>System: Case Dismissed
    end

    alt Participant Appeals
        Participant->>Appellate: Submits Appeal with Statement
        Note over Appellate: Appellate NOT in {R1, R2}
        Appellate->>Appellate: Reviews Case + Grounds
        Appellate-->>Participant: Decides Appeal (Upheld / Overturned)
    end
```

Reviewer Invariants:
1. `second_reviewer_id != assigned_reviewer_id`: Dual approval requires two distinct credentials.
2. `appellate_reviewer_id != assigned_reviewer_id` AND `appellate_reviewer_id != second_reviewer_id`: Appeals must be adjudicated with zero prior involvement in the initial ruling.
3. IDOR Scoping: Participants can only query and appeal their own integrity cases. Inquiries for other participants' cases return 404/403.

### 6. Immutable Published Results & Public Sanitization

1. **Version Lineage:** `PublishedResult` records are immutable once inserted. Amendments insert Version $K+1$ referencing `previous_version_id`, with explicit `amendment_reason` and approver signature.
2. **Deterministic Signed Hash:** Each published version computes a SHA-256 digest over the ranked rows, ensuring tamper detection.
3. **Strict Zero-PII Sanitization:** The public endpoint `GET /api/v1/results/events/{event_id}/public` maps participant records to:
   - `participant_display_name` (e.g. `SpeedDemon99`)
   - `rank_order`, `gross_wpm`, `net_wpm`, `accuracy_pct`, `arena_score`, `tier`
   - Omitted: User ID, email, real name, student/employee roll number, IP address, and unreviewed raw keystroke logs.

---

## Consequences & Trade-offs

### Positive
- **Tamper-Proof Standings:** Bitwise replay manifests allow independent re-scoring and audit verification at any time.
- **Fair Linguistic Measurement:** Non-ASCII alphabets and emoji typing challenges are measured accurately per grapheme cluster rather than byte length.
- **Due Process & Trust:** Two-person review for disqualifications and independent appeal adjudication prevent administrative bias.
- **Legal Compliance:** Strict privacy masking protects institutional participants and minors from public PII exposure.

### Negative / Trade-offs
- Replay manifests and detailed canonical segmentation add modest processing time ($< 5\text{ms}$ per attempt) and database storage.
- Disqualifications cannot be executed instantly by a single operator; a second qualified reviewer must log in and confirm.

