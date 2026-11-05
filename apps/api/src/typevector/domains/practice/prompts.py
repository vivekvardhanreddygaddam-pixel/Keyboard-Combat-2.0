"""TypeVector Arena — Curated Practice Prompt Library.

All prompts in this library are original, reviewed, and appropriately licensed.
Content sources:
- Original technical and educational texts crafted for TypeVector Arena.
- Public domain literature and classic quotations.
- Standard permissively licensed code patterns.
"""

from typing import Any

PRACTICE_PROMPTS: list[dict[str, Any]] = [
    # 1. Common Words
    {
        "id": "prompt-cw-01",
        "mode": "common_words",
        "title": "High-Frequency Core Vocabulary",
        "difficulty": "beginner",
        "language": "en",
        "source": "TypeVector Arena Original — General English frequency corpus",
        "content": (
            "about their would there which people could other think "
            "after first water where right those great state under "
            "world house again place point found world every never"
        ),
    },
    {
        "id": "prompt-cw-02",
        "mode": "common_words",
        "title": "Challenging Common Pairs",
        "difficulty": "intermediate",
        "language": "en",
        "source": "TypeVector Arena Original — Adjacent-key obstacle words",
        "content": (
            "between through because against without another thought "
            "picture question however morning together problem hundred "
            "surface produce certain pattern develop several general"
        ),
    },
    # 2. Sentences and Punctuation
    {
        "id": "prompt-sent-01",
        "mode": "sentences",
        "title": "Punctuation & Cadence Basics",
        "difficulty": "intermediate",
        "language": "en",
        "source": "TypeVector Arena Original",
        "content": (
            "Precision is not an accident; it is the deliberate discipline of "
            "every single keystroke. When you practice deliberately, speed "
            "naturally follows accuracy. Do not rush the difficult transitions!"
        ),
    },
    {
        "id": "prompt-sent-02",
        "mode": "sentences",
        "title": "Complex Punctuation & Quotes",
        "difficulty": "advanced",
        "language": "en",
        "source": "TypeVector Arena Original",
        "content": (
            '"Watch the timer," said the proctor, "and remember: gross speed '
            'means nothing if your net accuracy falters." The typist nodded, '
            "focused, and placed both hands on the home row (A-S-D-F / J-K-L-;)."
        ),
    },
    # 3. Short and Long Paragraphs
    {
        "id": "prompt-para-01",
        "mode": "paragraphs",
        "title": "The Evolution of Typewriters",
        "difficulty": "intermediate",
        "language": "en",
        "source": "TypeVector Arena Educational Historical Corpus",
        "content": (
            "Christopher Latham Sholes developed the QWERTY keyboard layout in the "
            "nineteenth century to prevent mechanical typebars from colliding during rapid "
            "typing. Although computer keyboards have long discarded mechanical arms, "
            "the layout remains universal across modern terminals and laptops."
        ),
    },
    {
        "id": "prompt-para-02",
        "mode": "paragraphs",
        "title": "Distributed Systems & Clocks",
        "difficulty": "advanced",
        "language": "en",
        "source": "TypeVector Arena Technical Prose Series",
        "content": (
            "In distributed computer systems, time is fundamentally non-uniform. "
            "Network latency fluctuates unpredictably, and unsynchronized local quartz "
            "clocks drift over elapsed seconds. For this reason, competitive tournament "
            "arenas must establish an authoritative central sequence rather than relying on "
            "unverified timestamps reported by client browser machines."
        ),
    },
    # 4. Numbers and Symbol Precision
    {
        "id": "prompt-num-01",
        "mode": "precision",
        "title": "Numerical Records & Percentages",
        "difficulty": "advanced",
        "language": "en",
        "source": "TypeVector Arena Numerical Challenge Series",
        "content": (
            "In 2024, the tournament recorded 1,480 participants across 12 divisions. "
            "Top performers averaged 142.5 WPM with 99.2% accuracy. Overall, 85% of "
            "final scores fell between 65.0 and 110.0 WPM; only 4.8% exceeded 130 WPM."
        ),
    },
    {
        "id": "prompt-sym-01",
        "mode": "precision",
        "title": "Mathematical & Structural Symbols",
        "difficulty": "expert",
        "language": "en",
        "source": "TypeVector Arena Symbol Benchmark",
        "content": (
            "Evaluate: [2 * (x + 5)] / {y - 3} = 100% & ratio != 0. "
            "Parameters: min_wpm >= 85, error_rate <= 0.02, #id = #1094. "
            "Keys: (~, !, @, #, $, %, ^, &, *, _, +, |, <, >)."
        ),
    },
    # 5. Code Snippets
    {
        "id": "prompt-code-01",
        "mode": "code",
        "title": "Python Async Task Queue",
        "difficulty": "intermediate",
        "language": "python",
        "source": "TypeVector Arena Open Engineering Library",
        "content": (
            "async def process_batch(items: list[str]) -> int:\n"
            "    count = 0\n"
            "    for item in items:\n"
            "        if item.strip():\n"
            "            await emit_event(item)\n"
            "            count += 1\n"
            "    return count"
        ),
    },
    {
        "id": "prompt-code-02",
        "mode": "code",
        "title": "JavaScript Sequence Gate",
        "difficulty": "advanced",
        "language": "javascript",
        "source": "TypeVector Arena Open Engineering Library",
        "content": (
            "function validateSequence(prevSeq, nextSeq) {\n"
            "  if (nextSeq !== prevSeq + 1) {\n"
            "    throw new Error(`Out of order: expected ${prevSeq + 1}`);\n"
            "  }\n"
            "  return { valid: true, sequence: nextSeq };\n"
            "}"
        ),
    },
    # 6. Timed Speed Sprint (60 seconds target)
    {
        "id": "prompt-sprint-01",
        "mode": "speed_sprint",
        "title": "One-Minute Speed Sprint",
        "difficulty": "intermediate",
        "language": "en",
        "source": "TypeVector Arena Sprint Series",
        "content": (
            "Quick bursts of clean typing require relaxed wrists and steady breathing. "
            "Do not tense your fingers as the countdown ticks away. Maintain a light "
            "touch on mechanical switches. Rhythm creates speed, while rushing only "
            "creates hesitation and repeated backspacing. Trust your muscle memory."
        ),
    },
    # 7. Accuracy Challenge (High-accuracy threshold)
    {
        "id": "prompt-acc-01",
        "mode": "accuracy_challenge",
        "title": "Zero-Tolerance Precision Drill",
        "difficulty": "expert",
        "language": "en",
        "source": "TypeVector Arena Accuracy Standards",
        "content": (
            "A single mistyped character in a critical command can corrupt an "
            "entire storage pool. Discipline demands that you verify every symbol "
            "before release. Accuracy is not a secondary goal; it is the sole "
            "foundation upon which durable velocity can be sustained."
        ),
    },
    # 8. Consistency / Endurance Challenge
    {
        "id": "prompt-endur-01",
        "mode": "endurance",
        "title": "Sustained Typing Marathon",
        "difficulty": "advanced",
        "language": "en",
        "source": "TypeVector Arena Endurance Track",
        "content": (
            "Endurance typing tests mental focus and physical posture over "
            "prolonged sessions. Typists who sprint aggressively in the first "
            "minute often suffer fatigue, erratic hand placement, and cascading "
            "mistakes later in the round. The master competitor settles into a "
            "sustainable cadence early, keeping fingertips centered and shoulders "
            "level. Every sentence flows with equal rhythm from beginning to end."
        ),
    },
    # 9. Diagnostic Practice
    {
        "id": "prompt-diag-01",
        "mode": "diagnostic",
        "title": "Diagnostic Keystroke Assessment",
        "difficulty": "intermediate",
        "language": "en",
        "source": "TypeVector Arena Diagnostic Calibration Test",
        "content": (
            "Diagnostic Test 1.0: Quick, brown foxes jump over 12 lazy dogs! "
            "Special symbols [({x = y * 4})]; check capital letters A, B, C. "
            "Analyze keystroke latencies and evaluate backspace frequencies."
        ),
    },
]


def get_all_prompts() -> list[dict[str, Any]]:
    """Return all curated practice prompts."""
    return PRACTICE_PROMPTS


def get_prompts_by_mode(mode: str) -> list[dict[str, Any]]:
    """Return practice prompts filtered by mode."""
    return [p for p in PRACTICE_PROMPTS if p["mode"] == mode]


def get_prompt_by_id(prompt_id: str) -> dict[str, Any] | None:
    """Return a single prompt by its unique ID."""
    for p in PRACTICE_PROMPTS:
        if p["id"] == prompt_id:
            return p
    return None
