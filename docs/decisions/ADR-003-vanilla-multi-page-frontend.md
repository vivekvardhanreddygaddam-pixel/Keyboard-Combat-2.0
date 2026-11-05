# ADR-003: Vanilla Multi-Page Application (MPA) Architecture for Frontend

**Status:** Accepted  
**Date:** 2026-11-03  
**Deciders:** Principal Product Architect, Core Engineering Team  
**Blueprint Reference:** Blueprint v4.0 — Frontend Architecture, Non-goals, Prompt 1, Prompt 3  

---

## 1. Context and Problem Statement
The frontend of TypeVector Arena serves three distinct user experiences:
1. Public visitors exploring events, rules, organizations, and official leaderboards.
2. Learners and competitors typing in practice modes and live ranked arena rounds.
3. Organizers operating live competitions, managing rosters, judging cases, and inspecting audit trails.

The frontend must provide absolute typing stability, predictable layout shifts, zero framework overhead, complete accessibility, and clean separation across public, participant, and organizer shells.

## 2. Decision Drivers
- Strict Blueprint v4.0 mandate: HTML5, CSS3, vanilla JavaScript ES modules; no React, Vue, Svelte, Next.js, or Angular.
- Typing surface mechanics require direct, uninterrupted control of DOM input events, IME composition, and selection ranges without interference from a virtual DOM or reactive scheduler.
- Multi-page experience: Distinct contexts (public landing vs intense competitive typing vs dense command center) benefit from clean URL routes, natural browser navigation, and localized memory lifecycles.
- High performance on lower-tier hardware and mobile browsers.

## 3. Considered Options
1. **Vanilla Multi-Page Architecture with Modern ES Modules (Chosen):**
   - Clean HTML pages served statically or built via Vite.
   - Reusable CSS design tokens and component primitives in vanilla CSS custom properties.
   - Modular JavaScript architecture: page controllers, shared navigation/header modules, isolated typing engine controllers, and thin API client modules.
2. **Single Page Application (SPA) with a Heavy Client-Side Framework:**
   - Explicitly prohibited by blueprint non-goals. Introduces substantial bundle weight, hydration complexities, and potential performance regressions during active typing.
3. **Custom "Micro-Framework" Reinventing Virtual DOM / React:**
   - Explicitly forbidden by project guidelines. Reinventing a bespoke reactive framework leads to maintainability debt and fragile event handling.

## 4. Decision Outcome
**Chosen Option:** Vanilla Multi-Page Architecture with Modern ES Modules.

### Architectural Breakdown:
- **Location:** `apps/web/`
- **Routing:** Standard browser page navigation across discrete HTML entry points (`/index.html`, `/events/index.html`, `/arena/index.html`, `/practice/index.html`, `/command/index.html`, etc.) paired with a lightweight client-side route resolver where sub-route shell handling is appropriate.
- **Design System:** Built entirely on CSS Custom Properties (`--tv-*` tokens for typography, spacing, surface colors, borders, shadows, focus rings, and motion) and semantic BEM-like class components (`.tv-btn`, `.tv-card`, `.tv-table`, `.tv-badge`, `.tv-input`).
- **Typing Engine Surface:** Dedicated vanilla JS controllers (`PracticeController`, `RankedTypingController`) that directly bind to `<textarea>` or `contenteditable` elements, manage focus recovery, monitor IME composition events, and update the display without re-rendering unaffected DOM nodes.

## 5. Consequences and Trade-offs
### Positive Consequences
- Zero runtime overhead: Initial page load is nearly instantaneous; scripts are lightweight and execute without framework initialization lag.
- Deterministic typing focus: No framework re-rendering race conditions can steal focus or discard keystrokes midway through an attempt.
- Semantic HTML and accessibility: Natural keyboard accessibility, native form submission fallbacks, and standard landmark roles (`<header>`, `<nav>`, `<main>`, `<footer>`).
- Strict security: Reduced attack surface with zero third-party UI library vulnerabilities.

### Negative Consequences / Accepted Trade-offs
- Manual DOM updates: Developers must write explicit DOM manipulation code for state transitions, requiring strict adherence to helper patterns (`tv-dom.js`).
- Shared state across pages (e.g., active user session) must be resolved via standard cookies and server API queries rather than an in-memory client store.

## 6. Compliance, Security, and Privacy Implications
- Content Security Policy (CSP) can be tightly configured since no inline scripts or unsafe evals are required.
- Session tokens are stored in `HttpOnly; Secure; SameSite=Strict` cookies, immune to client-side XSS exfiltration.

## 7. Validation Strategy
- Automated checks for HTML validation, keyboard navigation accessibility (Tab order, focus indicators), and Lighthouse performance scores.
- End-to-end tests validating page navigation, form submission, and typing engine stability across Chrome, Firefox, and Safari.

