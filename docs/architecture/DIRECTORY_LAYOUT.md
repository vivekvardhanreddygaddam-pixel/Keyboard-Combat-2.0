# TypeVector Arena — Proposed Monorepo Directory Layout (Documentation Only)

**Document Version:** 1.0.0  
**Date:** 2026-11-03  
**Status:** Architecture Specification  
**Note:** In strict compliance with Prompt 1 Task 10, this layout is documented here for architectural planning only. Application directories and source files will be scaffolded during Phase 2.

---

```text
e:/keyboard/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Automated linting, formatting, type checking, test runner
│       └── security-scan.yml      # Secret detection and dependency vulnerability scanner
├── apps/
│   ├── api/                       # Python / FastAPI Modular Monolith
│   │   ├── pyproject.toml         # Python service package configuration
│   │   ├── alembic.ini            # Database migration configuration
│   │   ├── migrations/            # Alembic schema version scripts
│   │   │   └── versions/
│   │   └── src/
│   │       └── typevector/
│   │           ├── __init__.py
│   │           ├── main.py        # FastAPI entrypoint, lifespan, CORS, middleware
│   │           ├── config.py      # Validated Pydantic settings
│   │           ├── database.py    # Async SQLAlchemy engine and session factory
│   │           ├── core/          # Shared infrastructure (logging, security, pagination)
│   │           └── domains/       # 16 Encapsulated Domain Packages
│   │               ├── identity/
│   │               ├── organizations/
│   │               ├── events/
│   │               ├── registrations/
│   │               ├── rounds/
│   │               ├── practice/
│   │               ├── curriculum/
│   │               ├── ranked_input/
│   │               ├── scoring/
│   │               ├── results/
│   │               ├── integrity_review/
│   │               ├── broadcast/
│   │               ├── notifications/
│   │               ├── exports/
│   │               ├── audit/
│   │               └── operations/
│   └── web/                       # Multi-Page Vanilla Frontend (HTML/CSS/JS)
│       ├── package.json           # Frontend package / dev tooling
│       ├── index.html             # Public home landing page
│       ├── events.html            # Public event discovery
│       ├── login.html             # Authentication shell
│       ├── register.html          # User registration shell
│       ├── account.html           # Participant account dashboard
│       ├── help.html              # Rules, scoring explanations, FAQ
│       ├── about.html             # About TypeVector Arena
│       ├── arena/                 # Participant ranked competition shell
│       │   ├── index.html         # Live arena lobby and countdown
│       │   └── attempt.html       # Active ranked typing surface
│       ├── practice/              # Independent practice typing shell
│       │   ├── index.html         # Mode selection and track dashboard
│       │   ├── session.html       # Practice typing workspace
│       │   └── review.html        # Detailed mistake diff analysis
│       ├── command/               # Organizer Command Center shell
│       │   ├── index.html         # Scoped command overview
│       │   ├── events.html        # Event management and draft wizard
│       │   ├── live.html          # Live operations & incident controls
│       │   ├── judging.html       # Integrity review queue & appeals
│       │   └── results.html       # Results preview, approval, publication
│       ├── css/                   # Design system tokens and styles
│       │   ├── tokens.css         # CSS Custom Properties (--tv-*)
│       │   ├── reset.css          # Semantic browser baseline
│       │   ├── layout.css         # Header, footer, grid, navigation
│       │   ├── components.css     # Buttons, cards, badges, tables
│       │   └── typing-engine.css  # Typing surface styles (zero-shift)
│       └── js/                    # Vanilla ES Modules
│           ├── app.js             # Shared bootstrap & navigation
│           ├── api-client.js      # Fetch wrapper with error envelopes
│           ├── dom-utils.js       # Safe DOM helpers
│           ├── practice-engine.js # Practice typing controller
│           └── ranked-engine.js   # WebSocket arena typing controller
├── packages/
│   └── api-contract/              # OpenAPI contract artifacts & schemas
├── workers/                       # Celery Background Workers
│   ├── celery_app.py              # Celery configuration & serializer setup
│   ├── tasks/                     # Async tasks (exports, notifications, retention)
│   └── outbox_dispatcher.py       # Transactional outbox reader daemon
├── tests/                         # Multi-Tier Automated Test Suites
│   ├── unit/                      # Fast unit and property tests
│   ├── golden_vectors/            # Pinned scorer and canonicalization vectors
│   ├── integration/               # PostgreSQL database integration tests
│   ├── concurrency/               # Race condition and WebSocket fencing tests
│   └── e2e/                       # Full browser user journey tests
├── infra/                         # Infrastructure & Deployment Configuration
│   ├── local/                     # Local developer compose setup
│   │   └── docker-compose.yml     # PostgreSQL + Redis local containers
│   ├── staging/                   # Staging deployment manifests
│   └── production/                # Production container assets
├── docs/                          # Project Documentation & Agent Handoff
│   ├── product/                   # Blueprint, source notes, RTM
│   ├── agent/                     # 5 Required Agent Handoff Documents
│   ├── decisions/                 # Architecture Decision Records (ADRs)
│   ├── architecture/              # Domain boundaries, standards, risks
│   └── runbooks/                  # Event operations and incident playbooks
├── .env.example                   # Safe configuration placeholder template
├── .gitignore                     # Git ignore rules for node, python, secrets
├── package.json                   # Root monorepo workspace scripts
├── pnpm-workspace.yaml            # pnpm workspace definition
├── pyproject.toml                 # Root Python project configuration
├── uv.lock                        # Deterministic Python lockfile (Phase 2)
└── README.md                      # Project overview and developer setup guide
```

