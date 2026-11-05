"""TypeVector Arena — Skill Tracks & Level Progression Catalog.

Defines the 7 initial curriculum tracks and 6 versioned levels per track.
All numerical thresholds in this module are explicitly designated as:
    CRITERIA_STATUS: "DRAFT_AWAITING_PRODUCT_APPROVAL"
    CRITERIA_VERSION: "2026.1-draft"

DISCLAIMER: Level titles (Foundation, Beginner, Developing, Intermediate, Advanced, Expert)
represent internal platform learning milestones and are NOT external professional certifications.
"""

from typing import Any

CRITERIA_VERSION = "2026.1-draft"
CRITERIA_STATUS = "DRAFT_AWAITING_PRODUCT_APPROVAL"

LEVEL_NAMES: dict[int, str] = {
    1: "Foundation",
    2: "Beginner",
    3: "Developing",
    4: "Intermediate",
    5: "Advanced",
    6: "Expert",
}

TRACKS_CATALOG: list[dict[str, Any]] = [
    # 1. Keyboard Fundamentals
    {
        "slug": "keyboard-fundamentals",
        "title": "Keyboard Fundamentals",
        "description": "Master home-row posture, key reaches, and finger recovery without looking at the keyboard.",
        "levels": [
            {
                "level_number": 1,
                "title": "Home Row Anchor",
                "min_wpm": 20.0,
                "min_accuracy_pct": 95.0,
                "pass_attempts_required": 2,
                "prompt_content": "asdf jkl; asdf jkl; fdsa ;lkj dad fad lad fall flask alas salad salsa",
            },
            {
                "level_number": 2,
                "title": "Top Row Reaches (E, R, T, U, I, O)",
                "min_wpm": 30.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 3,
                "prompt_content": "tree tire true fire root fruit sure tour pure ride ride user out our tour",
            },
            {
                "level_number": 3,
                "title": "Bottom Row Reaches (Z, X, C, V, B, N, M)",
                "min_wpm": 40.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "van cab back zoom exam calm move vine mix man ban box buzz cabin vocal",
            },
            {
                "level_number": 4,
                "title": "Full Alphabetical Coordination",
                "min_wpm": 50.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "the quick brown fox jumps over the lazy dog and pack my box with five dozen liquor jugs",
            },
            {
                "level_number": 5,
                "title": "Rapid Finger Independence",
                "min_wpm": 65.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": "complex finger acrobatics require disciplined home row recovery after every distant stroke",
            },
            {
                "level_number": 6,
                "title": "Instinctive Touch Mastery",
                "min_wpm": 80.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 5,
                "prompt_content": "unconscious finger fluency enables the mind to compose thoughts without acknowledging the physical keyboard",
            },
        ],
    },
    # 2. Word Accuracy
    {
        "slug": "word-accuracy",
        "title": "Word Accuracy",
        "description": "Eliminate hesitation on high-frequency vocabulary and tricky adjacent-key clusters.",
        "levels": [
            {
                "level_number": 1,
                "title": "Core Monosyllables",
                "min_wpm": 25.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 2,
                "prompt_content": "the and that have for with this from they word what some time make like look",
            },
            {
                "level_number": 2,
                "title": "Common Digraphs (TH, CH, SH, PH, WH)",
                "min_wpm": 35.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "think phase chart share while white thank which choose shape phrase phone when",
            },
            {
                "level_number": 3,
                "title": "Trisyllabic Rhythm",
                "min_wpm": 48.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "together beautiful important remember difficult dangerous consider continue general",
            },
            {
                "level_number": 4,
                "title": "Double Consonants & Alternating Keys",
                "min_wpm": 60.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": "success account address commit parallel suggest recommend immediate committee",
            },
            {
                "level_number": 5,
                "title": "Irregular Morphology",
                "min_wpm": 75.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": "rhythm bureaucracy silhouette surveillance sovereign conscious hierarchy phenomenon",
            },
            {
                "level_number": 6,
                "title": "Flawless Vocabulary Sprint",
                "min_wpm": 90.0,
                "min_accuracy_pct": 99.0,
                "pass_attempts_required": 5,
                "prompt_content": "encyclopedic precision requires deliberate repetition across idiosyncratic orthographic patterns",
            },
        ],
    },
    # 3. Sentence Fluency
    {
        "slug": "sentence-fluency",
        "title": "Sentence Fluency",
        "description": "Develop natural punctuation timing, capitalization cadence, and smooth phrasing.",
        "levels": [
            {
                "level_number": 1,
                "title": "Simple Statements & Periods",
                "min_wpm": 25.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 2,
                "prompt_content": "The morning sun rose early. We walked toward the lake. Birds sang in the quiet trees.",
            },
            {
                "level_number": 2,
                "title": "Commas & Compound Clauses",
                "min_wpm": 38.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "Although the wind was cold, we continued walking, and soon we reached the shelter.",
            },
            {
                "level_number": 3,
                "title": "Questions, Exclamations & Dialogue",
                "min_wpm": 50.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": '"Did you hear that sound?" asked Maya. "Hurry, we must reach the gate before dusk!"',
            },
            {
                "level_number": 4,
                "title": "Colons, Semicolons & Dashes",
                "min_wpm": 62.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": "Typing is rhythmic: each keystroke anticipates the next; sudden pauses disrupt momentum—stay relaxed.",
            },
            {
                "level_number": 5,
                "title": "Parenthetical Phrasing & Mixed Quotes",
                "min_wpm": 75.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": 'The report stated (with notable emphasis): "Competitors achieved higher net scores (above 95 WPM) through consistent pacing."',
            },
            {
                "level_number": 6,
                "title": "Literary Cadence",
                "min_wpm": 88.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 5,
                "prompt_content": "In that twilight hour, amidst swirling autumn leaves, the ancient bell tolled; time, it seemed, stood completely still.",
            },
        ],
    },
    # 4. Paragraph Fluency
    {
        "slug": "paragraph-fluency",
        "title": "Paragraph Fluency",
        "description": "Sustain speed and mental focus across multi-sentence paragraphs without buffer fatigue.",
        "levels": [
            {
                "level_number": 1,
                "title": "Short Descriptive Paragraph",
                "min_wpm": 28.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 2,
                "prompt_content": "The library was silent except for the gentle rustle of turning pages. Warm light poured across the wooden desks.",
            },
            {
                "level_number": 2,
                "title": "Two-Sentence Narrative",
                "min_wpm": 40.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "Exploration begins when familiar landmarks fade from view. Pioneers chart courses across unknown waters, relying on stars and unwavering courage.",
            },
            {
                "level_number": 3,
                "title": "Expository Prose",
                "min_wpm": 52.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "Modern computers process billions of mathematical instructions every second. Beneath sleek aluminum enclosures, microscopic transistors switch electrical currents with astronomical speed and microscopic precision.",
            },
            {
                "level_number": 4,
                "title": "Historical Synthesis",
                "min_wpm": 65.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": "The printing press transformed human culture by making written knowledge widely accessible. Where scribes once spent months copying single manuscripts, mechanical presses produced thousands of copies within weeks.",
            },
            {
                "level_number": 5,
                "title": "Scientific Argumentation",
                "min_wpm": 78.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": "Scientific progress relies upon reproducible empirical observation. Hypotheses must survive rigorous experimental scrutiny before earning acceptance within the broader research community.",
            },
            {
                "level_number": 6,
                "title": "Philosophical Thesis",
                "min_wpm": 90.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 5,
                "prompt_content": "Consciousness remains the profound mystery of modern cognitive philosophy. How subjective sensory experience arises from physical neural architecture challenges contemporary materialism.",
            },
        ],
    },
    # 5. Precision Typing (Numbers & Symbols)
    {
        "slug": "precision-typing",
        "title": "Precision Typing",
        "description": "Master top-row number reaches, math symbols, currency codes, and structural brackets.",
        "levels": [
            {
                "level_number": 1,
                "title": "Number Row Basics",
                "min_wpm": 18.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 2,
                "prompt_content": "10 20 30 40 50 60 70 80 90 100 2024 1984 2001 777 911 314 159 265",
            },
            {
                "level_number": 2,
                "title": "Common Financials & Dates",
                "min_wpm": 26.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "On 2024-05-12, revenue increased by 14.5% to $450,000, while operating expenses were held at $120,500.",
            },
            {
                "level_number": 3,
                "title": "Math Symbols & Formulas",
                "min_wpm": 36.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "Compute: (x + 5) * [y - 2] / 4 = 100% | alpha != beta & delta >= 0.05",
            },
            {
                "level_number": 4,
                "title": "Complex Technical Brackets",
                "min_wpm": 48.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": 'Config: { port: 8080, hosts: ["127.0.0.1", "192.168.1.1"], timeout: <300ms>, flag: #0xFA4B }',
            },
            {
                "level_number": 5,
                "title": "Dense Cryptographic Characters",
                "min_wpm": 60.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": "Token: @user#8492! Key: ~$4b*9^Z_1&%2+Q=7|? Check: (a < b && c > d || e == f)",
            },
            {
                "level_number": 6,
                "title": "Extreme Symbol Precision",
                "min_wpm": 72.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 5,
                "prompt_content": "Regex: ^[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,4}$ | Math: sum_{i=1}^{n} (x_i - mu)^2 / sigma^2",
            },
        ],
    },
    # 6. Code Typing
    {
        "slug": "code-typing",
        "title": "Code Typing",
        "description": "Type programming keywords, CamelCase, snake_case, syntax brackets, and indentation with zero mistakes.",
        "levels": [
            {
                "level_number": 1,
                "title": "Variables & Print Statements",
                "min_wpm": 18.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 2,
                "prompt_content": "const count = 10;\nlet total = 0;\nconsole.log(`Initial total: ${total}`);",
            },
            {
                "level_number": 2,
                "title": "Conditionals & Loops",
                "min_wpm": 28.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "for (let i = 0; i < items.length; i++) {\n    if (items[i] > threshold) {\n        total += items[i];\n    }\n}",
            },
            {
                "level_number": 3,
                "title": "Functions & Return Types",
                "min_wpm": 38.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": "async function fetchData(url: string): Promise<Response> {\n    const response = await fetch(url);\n    return response.json();\n}",
            },
            {
                "level_number": 4,
                "title": "Class Definitions & OOP",
                "min_wpm": 50.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 3,
                "prompt_content": "class EventEmitter {\n    constructor() {\n        this.listeners = new Map();\n    }\n    emit(event, payload) {\n        const handlers = this.listeners.get(event) || [];\n        handlers.forEach(fn => fn(payload));\n    }\n}",
            },
            {
                "level_number": 5,
                "title": "Rust Concurrency & Lifetimes",
                "min_wpm": 62.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 4,
                "prompt_content": "pub async fn handle_stream<T: Send + 'static>(rx: Receiver<T>) -> Result<(), AppError> {\n    while let Some(msg) = rx.recv().await {\n        process_message(msg)?;\n    }\n    Ok(())\n}",
            },
            {
                "level_number": 6,
                "title": "Complex Algorithm Implementation",
                "min_wpm": 75.0,
                "min_accuracy_pct": 99.0,
                "pass_attempts_required": 5,
                "prompt_content": "def binary_search(arr: list[int], target: int) -> int:\n    low, high = 0, len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1",
            },
        ],
    },
    # 7. Speed & Endurance
    {
        "slug": "speed-endurance",
        "title": "Speed & Endurance",
        "description": "Sustain high-velocity rhythm, fatigue resistance, and focus across extended sprints.",
        "levels": [
            {
                "level_number": 1,
                "title": "Cadence Foundation",
                "min_wpm": 35.0,
                "min_accuracy_pct": 96.0,
                "pass_attempts_required": 2,
                "prompt_content": "Keep wrists elevated and shoulders relaxed. Fast typing comes from rhythmic finger movement rather than heavy finger strikes. Maintain pace through every word.",
            },
            {
                "level_number": 2,
                "title": "Accelerating Pace",
                "min_wpm": 48.0,
                "min_accuracy_pct": 96.5,
                "pass_attempts_required": 3,
                "prompt_content": "Rhythm is velocity. When your fingers move in predictable cadence, word clusters flow together without hesitation. Breathe smoothly as your hands navigate the keys.",
            },
            {
                "level_number": 3,
                "title": "Sustained Velocity",
                "min_wpm": 60.0,
                "min_accuracy_pct": 97.0,
                "pass_attempts_required": 3,
                "prompt_content": "Endurance typing tests mental focus over prolonged attempts. Fast typists do not tense their hands; they maintain a soft, accurate touch across common language patterns.",
            },
            {
                "level_number": 4,
                "title": "High-Tempo Flow",
                "min_wpm": 72.0,
                "min_accuracy_pct": 97.5,
                "pass_attempts_required": 3,
                "prompt_content": "Consistency separates amateur speed from tournament precision. Every sentence requires equal concentration. Eliminate hesitation on transitional words and maintain momentum.",
            },
            {
                "level_number": 5,
                "title": "Marathon Sprint",
                "min_wpm": 85.0,
                "min_accuracy_pct": 98.0,
                "pass_attempts_required": 4,
                "prompt_content": "True speed demands that you type at the limit of your visual buffer without sacrificing accuracy. Control your breathing, anchor your core, and execute each stroke with certainty.",
            },
            {
                "level_number": 6,
                "title": "Peak Tournament Velocity",
                "min_wpm": 100.0,
                "min_accuracy_pct": 98.5,
                "pass_attempts_required": 5,
                "prompt_content": "Master competitors sustain triple-digit velocity while preserving near-perfect accuracy under strict tournament clocks. Complete focus transforms conscious effort into effortless motion.",
            },
        ],
    },
]


def get_tracks_catalog() -> list[dict[str, Any]]:
    """Return the complete skill track and level catalog."""
    return TRACKS_CATALOG


def get_track_by_slug(slug: str) -> dict[str, Any] | None:
    """Fetch track metadata and levels by slug."""
    for track in TRACKS_CATALOG:
        if track["slug"] == slug:
            return track
    return None


def get_track_level(slug: str, level_number: int) -> dict[str, Any] | None:
    """Fetch specific level within a track."""
    track = get_track_by_slug(slug)
    if not track:
        return None
    levels: list[dict[str, Any]] = track["levels"]
    for level in levels:
        if level["level_number"] == level_number:
            return level
    return None
