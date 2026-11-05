/**
 * TypeVector Arena — Organizer Command Center Controller
 * Pure Vanilla JavaScript ES Module for tournament administration, live operations,
 * roster readiness, integrity judging, result publication, and audit inspection.
 */

import { apiRequest } from "./api-client.js";
import { escapeHtml } from "./dom-utils.js";

class CommandCenter {
  constructor() {
    this.user = null;
    this.orgs = [];
    this.currentOrg = null;
    this.currentEvent = null;
    this.activeRoute = "/command";
    this.routeParams = {};
    this.pollTimer = null;

    this.container = document.getElementById("command-work-area");
    this.sidebar = document.getElementById("command-sidebar-nav");
    this.orgBadge = document.getElementById("command-tenant-badge");
    this.pageTitle = document.getElementById("command-page-title");
    this.pageLead = document.getElementById("command-page-lead");
    this.modalContainer = document.getElementById("command-modal-container");
  }

  async init() {
    // 1. Check authentication
    const authRes = await apiRequest("/api/v1/identity/me");
    if (!authRes.ok) {
      window.location.href = `/login/?returnUrl=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    this.user = authRes.data;

    // 2. Load user organizations
    const orgsRes = await apiRequest("/api/v1/organizations/user/me");
    if (orgsRes.ok && Array.isArray(orgsRes.data) && orgsRes.data.length > 0) {
      this.orgs = orgsRes.data;
      this.currentOrg = this.orgs[0];
    } else if (this.user.role === "platform_admin") {
      // Default placeholder org for platform admin
      this.currentOrg = { id: "00000000-0000-0000-0000-000000000000", name: "Platform Admin", slug: "platform-admin" };
    }

    if (this.orgBadge && this.currentOrg) {
      this.orgBadge.textContent = `TENANT: ${this.currentOrg.name.toUpperCase()}`;
    }

    // 3. Setup popstate listener for back/forward browser navigation
    window.addEventListener("popstate", () => {
      this.handleRoute(window.location.pathname + window.location.search);
    });

    // 4. Initial route resolution
    this.handleRoute(window.location.pathname + window.location.search);
  }

  navigate(path, pushState = true) {
    if (pushState) {
      window.history.pushState({}, "", path);
    }
    this.handleRoute(path);
  }

  parsePath(urlPath) {
    // Clean path, strip /command prefix if present
    const clean = urlPath.split("?")[0].replace(/\/index\.html$/, "");
    const query = new URLSearchParams(urlPath.includes("?") ? urlPath.split("?")[1] : "");

    // Check for query route override if served from static file
    if (query.get("route")) {
      return { route: query.get("route"), params: { eventId: query.get("eventId") } };
    }

    // Direct path routing
    const parts = clean.split("/").filter(Boolean);
    // e.g. ["command"], ["command", "events"], ["command", "events", "123", "live"]
    if (parts.length <= 1) return { route: "overview", params: {} };
    if (parts[1] === "organizations") return { route: "organizations", params: {} };
    if (parts[1] === "organization" && parts[2] === "members") return { route: "organization_members", params: {} };
    if (parts[1] === "operations") return { route: "operations", params: {} };
    if (parts[1] === "events") {
      if (parts.length === 2) return { route: "events_list", params: {} };
      if (parts[2] === "new") return { route: "events_new", params: {} };
      const eventId = parts[2];
      if (parts.length === 3) return { route: "event_summary", params: { eventId } };
      const sub = parts[3];
      return { route: `event_${sub}`, params: { eventId } };
    }
    return { route: "overview", params: {} };
  }

  async handleRoute(path) {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }

    const { route, params } = this.parsePath(path);
    this.activeRoute = route;
    this.routeParams = params;

    this.updateSidebarNav();

    if (params.eventId && (!this.currentEvent || this.currentEvent.id !== params.eventId)) {
      const evRes = await apiRequest(`/api/v1/events/${params.eventId}`);
      if (evRes.ok) {
        this.currentEvent = evRes.data;
      }
    }

    switch (route) {
      case "overview":
        await this.renderOverview();
        break;
      case "organizations":
        await this.renderOrganizations();
        break;
      case "organization_members":
        await this.renderOrgMembers();
        break;
      case "events_list":
        await this.renderEventsList();
        break;
      case "events_new":
        await this.renderEventWizard();
        break;
      case "event_summary":
        await this.renderEventSummary(params.eventId);
        break;
      case "event_rounds":
        await this.renderRoundsEditor(params.eventId);
        break;
      case "event_roster":
        await this.renderRoster(params.eventId);
        break;
      case "event_live":
        await this.renderLiveOperations(params.eventId);
        break;
      case "event_judging":
        await this.renderJudging(params.eventId);
        break;
      case "event_results":
        await this.renderResults(params.eventId);
        break;
      case "event_reports":
        await this.renderReports(params.eventId);
        break;
      case "event_audit":
        await this.renderAuditTrail(params.eventId);
        break;
      case "operations":
        await this.renderPlatformHealth();
        break;
      default:
        await this.renderOverview();
    }
  }

  updateSidebarNav() {
    if (!this.sidebar) return;
    const eventId = this.currentEvent ? this.currentEvent.id : null;

    let navHtml = `
      <div style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); text-transform: uppercase; padding: 0.5rem 0.75rem; letter-spacing: 0.05em; font-weight: 700;">Navigation</div>
      <a href="/command" data-link="overview" class="tv-command-nav-item ${this.activeRoute === "overview" ? "tv-command-nav-item--active" : ""}">
        <span>📊</span> Overview
      </a>
      <a href="/command/events" data-link="events_list" class="tv-command-nav-item ${this.activeRoute === "events_list" || this.activeRoute === "events_new" ? "tv-command-nav-item--active" : ""}">
        <span>🗓️</span> Events
      </a>
      <a href="/command/organizations" data-link="organizations" class="tv-command-nav-item ${this.activeRoute === "organizations" ? "tv-command-nav-item--active" : ""}">
        <span>🏢</span> Organizations
      </a>
      <a href="/command/organization/members" data-link="organization_members" class="tv-command-nav-item ${this.activeRoute === "organization_members" ? "tv-command-nav-item--active" : ""}">
        <span>👥</span> Org Members
      </a>
      <a href="/command/operations" data-link="operations" class="tv-command-nav-item ${this.activeRoute === "operations" ? "tv-command-nav-item--active" : ""}">
        <span>🩺</span> Platform Health
      </a>
    `;

    if (eventId) {
      navHtml += `
        <div style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); text-transform: uppercase; padding: 1rem 0.75rem 0.5rem; letter-spacing: 0.05em; font-weight: 700; border-top: 1px solid var(--tv-border-default); margin-top: 0.5rem;">
          Event Controls
        </div>
        <div style="padding: 0 0.75rem 0.5rem; font-size: var(--tv-text-xs); color: var(--tv-color-accent); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
          ${escapeHtml(this.currentEvent.title)}
        </div>
        <a href="/command/events/${eventId}" data-link="event_summary" class="tv-command-nav-item ${this.activeRoute === "event_summary" ? "tv-command-nav-item--active" : ""}">
          <span>📋</span> Summary & Rules
        </a>
        <a href="/command/events/${eventId}/rounds" data-link="event_rounds" class="tv-command-nav-item ${this.activeRoute === "event_rounds" ? "tv-command-nav-item--active" : ""}">
          <span>⏱️</span> Rounds Editor
        </a>
        <a href="/command/events/${eventId}/roster" data-link="event_roster" class="tv-command-nav-item ${this.activeRoute === "event_roster" ? "tv-command-nav-item--active" : ""}">
          <span>👥</span> Roster & Check-In
        </a>
        <a href="/command/events/${eventId}/live" data-link="event_live" class="tv-command-nav-item ${this.activeRoute === "event_live" ? "tv-command-nav-item--active" : ""}">
          <span>⚡</span> Live Controls
        </a>
        <a href="/command/events/${eventId}/judging" data-link="event_judging" class="tv-command-nav-item ${this.activeRoute === "event_judging" ? "tv-command-nav-item--active" : ""}">
          <span>⚖️</span> Judging & Appeals
        </a>
        <a href="/command/events/${eventId}/results" data-link="event_results" class="tv-command-nav-item ${this.activeRoute === "event_results" ? "tv-command-nav-item--active" : ""}">
          <span>📜</span> Results & Publish
        </a>
        <a href="/command/events/${eventId}/reports" data-link="event_reports" class="tv-command-nav-item ${this.activeRoute === "event_reports" ? "tv-command-nav-item--active" : ""}">
          <span>📥</span> Reports & Exports
        </a>
        <a href="/command/events/${eventId}/audit" data-link="event_audit" class="tv-command-nav-item ${this.activeRoute === "event_audit" ? "tv-command-nav-item--active" : ""}">
          <span>🔍</span> Audit Trail
        </a>
      `;
    }

    this.sidebar.innerHTML = navHtml;

    // Attach click listeners for SPA navigation
    this.sidebar.querySelectorAll("a[data-link]").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const href = link.getAttribute("href");
        this.navigate(href);
      });
    });
  }

  // ==========================================
  // VIEW RENDERERS
  // ==========================================

  async renderOverview() {
    this.setTitle("Organizer Command Center", "Operational dashboard for live typing tournaments, roster controls, and audit integrity.");
    this.container.innerHTML = `<div class="tv-card"><p>Loading command overview...</p></div>`;

    if (!this.currentOrg) {
      this.container.innerHTML = `
        <div class="tv-alert tv-alert--warning">
          <div>No organization found. Please create or join an organization to administer competitions.</div>
        </div>
      `;
      return;
    }

    const eventsRes = await apiRequest(`/api/v1/events/organization/${this.currentOrg.id}`);
    const events = eventsRes.ok ? eventsRes.data : [];

    const activeEvents = events.filter((e) => ["registration_open", "check_in_open", "ready", "live", "paused"].includes(e.status));
    const draftEvents = events.filter((e) => e.status === "draft");
    const completedEvents = events.filter((e) => ["completed", "review", "results_published", "amended"].includes(e.status));

    this.container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-6);">
        <div>
          <span class="tv-badge tv-badge--saved">${escapeHtml(this.currentOrg.name)}</span>
          <span style="color: var(--tv-text-muted); font-size: var(--tv-text-sm); margin-left: 0.5rem;">${events.length} total competitions</span>
        </div>
        <button id="btn-create-event-top" class="tv-btn tv-btn--primary tv-btn--sm">+ Create Draft Event</button>
      </div>

      <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <span class="tv-metric-item__label">Active Competitions</span>
          <div class="tv-metric-item__value" style="color: var(--tv-status-live);">${activeEvents.length}</div>
          <span class="tv-badge tv-badge--saved" style="margin-top: 0.5rem;">Operational</span>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Drafts in Setup</span>
          <div class="tv-metric-item__value" style="color: var(--tv-status-provisional);">${draftEvents.length}</div>
          <span class="tv-badge tv-badge--pending" style="margin-top: 0.5rem;">Configuring</span>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Completed Tournaments</span>
          <div class="tv-metric-item__value" style="color: var(--tv-text-primary);">${completedEvents.length}</div>
          <span class="tv-badge tv-badge--official" style="margin-top: 0.5rem;">Published</span>
        </div>
      </div>

      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Recent Competitions</h2>
        </div>
        <div class="tv-card__body">
          ${
            events.length === 0
              ? `<div style="text-align: center; padding: var(--tv-space-6); color: var(--tv-text-muted);">
                  <p>No competitions configured yet for ${escapeHtml(this.currentOrg.name)}.</p>
                  <button id="btn-create-event-empty" class="tv-btn tv-btn--primary tv-btn--sm" style="margin-top: 1rem;">Create First Event</button>
                </div>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr>
                        <th>Title / Slug</th>
                        <th>Status</th>
                        <th>Capacity</th>
                        <th>Prize Ruleset</th>
                        <th>Version</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${events
                        .slice(0, 10)
                        .map(
                          (ev) => `
                        <tr>
                          <td>
                            <strong>${escapeHtml(ev.title)}</strong><br>
                            <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); font-family: var(--tv-font-mono);">${escapeHtml(ev.slug)}</span>
                          </td>
                          <td><span class="tv-badge ${this.getStatusBadgeClass(ev.status)}">${ev.status.toUpperCase()}</span></td>
                          <td>${ev.capacity}</td>
                          <td>${ev.is_prize_event ? `<span class="tv-badge tv-badge--provisional">Prize (${ev.ruleset_approval_status})</span>` : "Friendly/Standard"}</td>
                          <td class="tv-table__cell--mono">v${ev.version}</td>
                          <td>
                            <a href="/command/events/${ev.id}" data-event-link="${ev.id}" class="tv-btn tv-btn--outline tv-btn--sm">Manage</a>
                          </td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    document.querySelectorAll("[id^='btn-create-event']").forEach((btn) => {
      btn.addEventListener("click", () => this.navigate("/command/events/new"));
    });

    this.container.querySelectorAll("a[data-event-link]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        this.navigate(a.getAttribute("href"));
      });
    });
  }

  async renderOrganizations() {
    this.setTitle("Organizations & Tenants", "Select active administration tenant or provision a new organization boundary.");

    const rows = this.orgs
      .map(
        (o) => `
      <tr>
        <td><strong>${escapeHtml(o.name)}</strong></td>
        <td class="tv-table__cell--mono">${escapeHtml(o.slug)}</td>
        <td><span class="tv-badge tv-badge--saved">${o.status.toUpperCase()}</span></td>
        <td>
          ${
            this.currentOrg && this.currentOrg.id === o.id
              ? `<span class="tv-badge tv-badge--official">ACTIVE TENANT</span>`
              : `<button class="tv-btn tv-btn--outline tv-btn--sm" data-switch-org="${o.id}">Switch To Org</button>`
          }
        </td>
      </tr>
    `
      )
      .join("");

    this.container.innerHTML = `
      <div class="tv-grid-2" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">My Organizations</h2>
          </div>
          <div class="tv-card__body">
            <div class="tv-table-wrapper">
              <table class="tv-table">
                <thead>
                  <tr><th>Name</th><th>Slug</th><th>Status</th><th>Action</th></tr>
                </thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Provision New Organization</h2>
          </div>
          <div class="tv-card__body">
            <form id="form-create-org">
              <div class="tv-form-group">
                <label class="tv-label" for="org-name">Organization Name</label>
                <input class="tv-input" id="org-name" required minlength="2" placeholder="e.g. Stanford Typing Guild">
              </div>
              <div class="tv-form-group">
                <label class="tv-label" for="org-slug">URL Slug</label>
                <input class="tv-input" id="org-slug" required pattern="^[a-z0-9-]+$" placeholder="e.g. stanford-typing">
              </div>
              <div id="org-error-msg" style="color: var(--tv-status-error); margin-bottom: 1rem; display: none;"></div>
              <button type="submit" class="tv-btn tv-btn--primary">Create Organization</button>
            </form>
          </div>
        </div>
      </div>
    `;

    this.container.querySelectorAll("[data-switch-org]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-switch-org");
        const found = this.orgs.find((o) => o.id === id);
        if (found) {
          this.currentOrg = found;
          if (this.orgBadge) this.orgBadge.textContent = `TENANT: ${found.name.toUpperCase()}`;
          this.renderOrganizations();
        }
      });
    });

    const form = document.getElementById("form-create-org");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("org-name").value.trim();
      const slug = document.getElementById("org-slug").value.trim().toLowerCase();
      const errBox = document.getElementById("org-error-msg");

      const res = await apiRequest("/api/v1/organizations", {
        method: "POST",
        body: JSON.stringify({ name, slug }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Failed to create organization";
        errBox.style.display = "block";
      } else {
        this.orgs.push(res.data);
        this.currentOrg = res.data;
        if (this.orgBadge) this.orgBadge.textContent = `TENANT: ${res.data.name.toUpperCase()}`;
        this.renderOrganizations();
      }
    });
  }

  async renderEventsList() {
    this.setTitle("Tournament Directory", `All competitions managed under ${this.currentOrg?.name || "active tenant"}.`);

    if (!this.currentOrg) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--warning">Select an organization first.</div>`;
      return;
    }

    const res = await apiRequest(`/api/v1/events/organization/${this.currentOrg.id}`);
    const events = res.ok ? res.data : [];

    this.container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-4);">
        <input class="tv-input" id="search-events-input" placeholder="Search events by title or slug..." style="max-width: 320px;">
        <button id="btn-events-new" class="tv-btn tv-btn--primary tv-btn--sm">+ New Event Wizard</button>
      </div>

      <div class="tv-table-wrapper">
        <table class="tv-table" id="events-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Slug</th>
              <th>Status</th>
              <th>Capacity</th>
              <th>Version</th>
              <th>Created</th>
              <th>Controls</th>
            </tr>
          </thead>
          <tbody>
            ${
              events.length === 0
                ? `<tr><td colspan="7" style="text-align: center; color: var(--tv-text-muted);">No events found.</td></tr>`
                : events
                    .map(
                      (e) => `
                  <tr>
                    <td><strong>${escapeHtml(e.title)}</strong></td>
                    <td class="tv-table__cell--mono">${escapeHtml(e.slug)}</td>
                    <td><span class="tv-badge ${this.getStatusBadgeClass(e.status)}">${e.status.toUpperCase()}</span></td>
                    <td>${e.capacity}</td>
                    <td class="tv-table__cell--mono">v${e.version}</td>
                    <td>${new Date(e.created_at).toLocaleDateString()}</td>
                    <td>
                      <a href="/command/events/${e.id}" data-event-link="${e.id}" class="tv-btn tv-btn--outline tv-btn--sm">Manage</a>
                    </td>
                  </tr>
                `
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    `;

    document.getElementById("btn-events-new")?.addEventListener("click", () => this.navigate("/command/events/new"));

    this.container.querySelectorAll("a[data-event-link]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        this.navigate(a.getAttribute("href"));
      });
    });

    // Search filter
    document.getElementById("search-events-input")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      document.querySelectorAll("#events-table tbody tr").forEach((tr) => {
        const text = tr.textContent.toLowerCase();
        tr.style.display = text.includes(q) ? "" : "none";
      });
    });
  }

  async renderEventWizard() {
    this.setTitle("Draft Event Wizard", "Configure competition details, eligibility, duration, and immutable ruleset profile.");

    this.container.innerHTML = `
      <div class="tv-card" style="max-width: 680px; margin: 0 auto;">
        <div class="tv-card__header">
          <h2 class="tv-card__title">Create Draft Competition</h2>
          <p class="tv-card__subtitle">Rules freeze permanently upon leaving DRAFT status.</p>
        </div>
        <div class="tv-card__body">
          <form id="form-event-wizard">
            <div class="tv-form-group">
              <label class="tv-label" for="wiz-title">Competition Title</label>
              <input class="tv-input" id="wiz-title" required minlength="3" placeholder="e.g. 2026 Winter Sprint Championship">
            </div>

            <div class="tv-form-group">
              <label class="tv-label" for="wiz-slug">Event Slug (URL-safe identifier)</label>
              <input class="tv-input" id="wiz-slug" required pattern="^[a-z0-9-]+$" placeholder="e.g. winter-sprint-2026">
            </div>

            <div class="tv-form-group">
              <label class="tv-label" for="wiz-description">Description & Rules Summary</label>
              <textarea class="tv-input" id="wiz-description" rows="3" placeholder="Participant guidelines, eligibility requirements, rules..."></textarea>
            </div>

            <div class="tv-grid-2">
              <div class="tv-form-group">
                <label class="tv-label" for="wiz-capacity">Max Participant Capacity</label>
                <input class="tv-input" id="wiz-capacity" type="number" value="100" min="2" max="10000" required>
              </div>
              <div class="tv-form-group">
                <label class="tv-label" for="wiz-duration">Default Round Duration (seconds)</label>
                <input class="tv-input" id="wiz-duration" type="number" value="60" min="10" max="3600" required>
              </div>
            </div>

            <div class="tv-grid-2">
              <div class="tv-form-group">
                <label class="tv-label" for="wiz-min-accuracy">Minimum Required Accuracy (%)</label>
                <input class="tv-input" id="wiz-min-accuracy" type="number" step="0.5" value="90.0" min="50" max="100" required>
              </div>
              <div class="tv-form-group">
                <label class="tv-label" for="wiz-formula">Scoring Engine</label>
                <select class="tv-input" id="wiz-formula" disabled>
                  <option value="arena-score-v1">arena-score-v1 (Pinned Integer Formula)</option>
                </select>
              </div>
            </div>

            <div class="tv-form-group" style="margin-top: var(--tv-space-3);">
              <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" id="wiz-is-prize">
                <span>Sanctioned Prize Competition (Requires Tournament Director rule approval prior to official publication)</span>
              </label>
            </div>

            <div id="wiz-error" style="color: var(--tv-status-error); margin: 1rem 0; display: none;"></div>

            <div style="display: flex; justify-content: flex-end; gap: var(--tv-space-3); margin-top: var(--tv-space-6);">
              <button type="button" class="tv-btn tv-btn--outline" id="wiz-cancel">Cancel</button>
              <button type="submit" class="tv-btn tv-btn--primary">Create Draft Event</button>
            </div>
          </form>
        </div>
      </div>
    `;

    document.getElementById("wiz-cancel")?.addEventListener("click", () => this.navigate("/command/events"));

    const form = document.getElementById("form-event-wizard");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = document.getElementById("wiz-error");
      const title = document.getElementById("wiz-title").value.trim();
      const slug = document.getElementById("wiz-slug").value.trim().toLowerCase();
      const description = document.getElementById("wiz-description").value.trim();
      const capacity = parseInt(document.getElementById("wiz-capacity").value, 10);
      const duration = parseInt(document.getElementById("wiz-duration").value, 10);
      const minAccuracy = parseFloat(document.getElementById("wiz-min-accuracy").value);
      const isPrize = document.getElementById("wiz-is-prize").checked;

      const payload = {
        organization_id: this.currentOrg.id,
        slug,
        title,
        description,
        capacity,
        duration_seconds: duration,
        min_accuracy_pct: minAccuracy,
        scoring_formula: "arena-score-v1",
        is_prize_event: isPrize,
      };

      const res = await apiRequest("/api/v1/events", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Failed to create event";
        errBox.style.display = "block";
      } else {
        this.navigate(`/command/events/${res.data.id}`);
      }
    });
  }

  async renderEventSummary(eventId) {
    const res = await apiRequest(`/api/v1/events/${eventId}/detail`);
    if (!res.ok) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--error">Failed to load event details: ${res.error}</div>`;
      return;
    }
    const event = res.data;
    this.currentEvent = event;
    this.setTitle(`Event: ${event.title}`, `Status: ${event.status.toUpperCase()} | Version: ${event.version}`);

    const isDraft = event.status === "draft";
    const ruleset = event.rulesets && event.rulesets[0];

    this.container.innerHTML = `
      <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <span class="tv-metric-item__label">Lifecycle State</span>
          <div class="tv-metric-item__value">
            <span class="tv-badge ${this.getStatusBadgeClass(event.status)}">${event.status.toUpperCase()}</span>
          </div>
          <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.5rem; display: block;">Optimistic Lock: v${event.version}</span>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Capacity Limit</span>
          <div class="tv-metric-item__value">${event.capacity}</div>
          <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.5rem; display: block;">Participants</span>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Prize Sanctioning</span>
          <div class="tv-metric-item__value" style="font-size: var(--tv-text-base);">
            ${event.is_prize_event ? "Prize Event" : "Friendly / Standard"}
          </div>
          <span class="tv-badge ${event.ruleset_approval_status === "approved" ? "tv-badge--official" : "tv-badge--provisional"}" style="margin-top: 0.5rem;">
            ${event.ruleset_approval_status.toUpperCase()}
          </span>
        </div>
      </div>

      <div class="tv-grid-2" style="margin-bottom: var(--tv-space-6);">
        <!-- Ruleset Card -->
        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Competition Ruleset Specifications</h2>
            <span class="tv-badge ${isDraft ? "tv-badge--pending" : "tv-badge--official"}">
              ${isDraft ? "Editable Draft" : "Permanently Frozen"}
            </span>
          </div>
          <div class="tv-card__body">
            ${
              ruleset
                ? `
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: var(--tv-text-sm);">
                <div><strong>Scoring Engine:</strong> <span class="tv-table__cell--mono">${escapeHtml(ruleset.scoring_formula)}</span></div>
                <div><strong>Version Number:</strong> v${ruleset.version_number}</div>
                <div><strong>Default Duration:</strong> ${ruleset.duration_seconds}s</div>
                <div><strong>Min Accuracy:</strong> ${ruleset.min_accuracy_pct}%</div>
              </div>
              <div style="margin-top: 1rem; font-size: var(--tv-text-xs); color: var(--tv-text-muted);">
                Canonicalization: <code>${escapeHtml(ruleset.ruleset_json.canonicalization || "unicode-paragraph-v1")}</code>
              </div>
            `
                : `<p>No ruleset found.</p>`
            }
          </div>
        </div>

        <!-- Lifecycle Transition Console -->
        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Lifecycle State Actions</h2>
            <span class="tv-badge tv-badge--saved">Server Gated</span>
          </div>
          <div class="tv-card__body">
            <p style="font-size: var(--tv-text-xs); color: var(--tv-text-secondary); margin-bottom: 1rem;">
              Transitions must satisfy published prerequisite rules. Stale version submissions are rejected with 409 Conflict.
            </p>
            <div id="lifecycle-actions" style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
              ${this.renderTransitionButtons(event)}
            </div>
            <div id="transition-error" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); margin-top: 0.75rem; display: none;"></div>
          </div>
        </div>
      </div>

      <!-- Quick Action Jump Links -->
      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Event Management Workflows</h2>
        </div>
        <div class="tv-card__body" style="display: flex; flex-wrap: wrap; gap: var(--tv-space-3);">
          <a href="/command/events/${event.id}/rounds" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Configure Rounds</a>
          <a href="/command/events/${event.id}/roster" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Manage Roster</a>
          <a href="/command/events/${event.id}/live" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Live Operations & Incidents</a>
          <a href="/command/events/${event.id}/judging" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Judging & Appeals</a>
          <a href="/command/events/${event.id}/results" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Standings & Publication</a>
          <a href="/command/events/${event.id}/reports" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Exports & Reports</a>
          <a href="/command/events/${event.id}/audit" data-nav class="tv-btn tv-btn--outline tv-btn--sm">Audit Trail</a>
        </div>
      </div>
    `;

    this.container.querySelectorAll("a[data-nav]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        this.navigate(a.getAttribute("href"));
      });
    });

    this.attachTransitionHandlers(event);
  }

  renderTransitionButtons(event) {
    const s = event.status;
    const v = event.version;
    const btns = [];

    if (s === "draft") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="published" data-ver="${v}">Publish Event (Freeze Rules)</button>`);
      btns.push(`<button class="tv-btn tv-btn--outline tv-btn--sm" data-trans="cancelled" data-ver="${v}">Cancel Draft</button>`);
    } else if (s === "published") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="registration_open" data-ver="${v}">Open Registration</button>`);
      btns.push(`<button class="tv-btn tv-btn--outline tv-btn--sm" data-trans="cancelled" data-ver="${v}">Cancel Event</button>`);
    } else if (s === "registration_open") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="check_in_open" data-ver="${v}">Open Check-In Window</button>`);
      btns.push(`<button class="tv-btn tv-btn--outline tv-btn--sm" data-trans="cancelled" data-ver="${v}">Cancel Event</button>`);
    } else if (s === "check_in_open") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="ready" data-ver="${v}">Declare Event Ready</button>`);
    } else if (s === "ready") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="live" data-ver="${v}">Start Event Live (Sweep No-Shows)</button>`);
    } else if (s === "live") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="completed" data-ver="${v}">Complete Competition</button>`);
    } else if (s === "completed") {
      btns.push(`<button class="tv-btn tv-btn--primary tv-btn--sm" data-trans="review" data-ver="${v}">Begin Integrity Review</button>`);
    } else if (s === "review") {
      btns.push(`<a href="/command/events/${event.id}/results" data-nav class="tv-btn tv-btn--primary tv-btn--sm">Proceed to Results Publication</a>`);
    } else if (s === "results_published" || s === "amended") {
      btns.push(`<button class="tv-btn tv-btn--outline tv-btn--sm" data-trans="archived" data-ver="${v}">Archive Event</button>`);
    }
    return btns.join("");
  }

  attachTransitionHandlers(event) {
    this.container.querySelectorAll("[data-trans]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const target = btn.getAttribute("data-trans");
        const ver = parseInt(btn.getAttribute("data-ver"), 10);
        const errBox = document.getElementById("transition-error");

        const promptReason = prompt(`Enter mandatory reason for transitioning event to ${target.toUpperCase()}:`, `Transition to ${target}`);
        if (!promptReason) return;

        btn.disabled = true;
        btn.textContent = "Transitioning...";

        const res = await apiRequest(`/api/v1/events/${event.id}/transition`, {
          method: "POST",
          body: JSON.stringify({
            target_status: target,
            expected_version: ver,
            reason: promptReason,
          }),
        });

        if (!res.ok) {
          errBox.textContent = res.error || "Transition rejected";
          errBox.style.display = "block";
          btn.disabled = false;
          btn.textContent = "Retry";
        } else {
          this.renderEventSummary(event.id);
        }
      });
    });
  }

  async renderRoundsEditor(eventId) {
    this.setTitle("Rounds Configuration & Prompts", "Add rounds, assign immutable prompts, and set durations. Frozen after publication.");

    const [eventRes, roundsRes] = await Promise.all([
      apiRequest(`/api/v1/events/${eventId}`),
      apiRequest(`/api/v1/rounds/event/${eventId}`),
    ]);

    if (!eventRes.ok) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--error">Event not found.</div>`;
      return;
    }

    const event = eventRes.data;
    const rounds = roundsRes.ok ? roundsRes.data : [];
    const isDraft = event.status === "draft";

    this.container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-4);">
        <div>
          <span class="tv-badge ${isDraft ? "tv-badge--pending" : "tv-badge--official"}">
            ${isDraft ? "Draft Mode: Rounds Configurable" : "Published: Rounds Locked"}
          </span>
        </div>
        ${isDraft ? `<button id="btn-add-round" class="tv-btn tv-btn--primary tv-btn--sm">+ Add Competition Round</button>` : ""}
      </div>

      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Scheduled Rounds (${rounds.length})</h2>
        </div>
        <div class="tv-card__body">
          ${
            rounds.length === 0
              ? `<div style="text-align: center; padding: 2rem; color: var(--tv-text-muted);">No rounds created yet. Add at least 1 round before publishing the event.</div>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr><th>Seq #</th><th>Status</th><th>Version</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                      ${rounds
                        .map(
                          (r) => `
                        <tr>
                          <td><strong>Round ${r.sequence_number}</strong></td>
                          <td><span class="tv-badge ${this.getStatusBadgeClass(r.status)}">${r.status.toUpperCase()}</span></td>
                          <td class="tv-table__cell--mono">v${r.version}</td>
                          <td>
                            <button class="tv-btn tv-btn--outline tv-btn--sm" data-view-prompt="${r.id}">View / Pin Prompt</button>
                          </td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    document.getElementById("btn-add-round")?.addEventListener("click", () => this.showAddRoundModal(eventId, rounds.length + 1));

    this.container.querySelectorAll("[data-view-prompt]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const roundId = btn.getAttribute("data-view-prompt");
        this.showPromptsModal(roundId, eventId, isDraft);
      });
    });
  }

  showAddRoundModal(eventId, nextSeq) {
    this.openModal({
      title: `Add Round ${nextSeq}`,
      body: `
        <form id="form-modal-add-round">
          <div class="tv-form-group">
            <label class="tv-label">Sequence Number</label>
            <input class="tv-input" id="round-seq" type="number" value="${nextSeq}" min="1" max="100" required>
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Initial Challenge Prompt Text</label>
            <textarea class="tv-input" id="round-prompt" rows="4" minlength="5" placeholder="Enter paragraph text or code challenge..." required></textarea>
          </div>
          <div id="modal-round-err" style="color: var(--tv-status-error); margin: 0.5rem 0; display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Create Round</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-modal-add-round")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const seq = parseInt(document.getElementById("round-seq").value, 10);
      const prompt = document.getElementById("round-prompt").value.trim();
      const errBox = document.getElementById("modal-round-err");

      const res = await apiRequest("/api/v1/rounds", {
        method: "POST",
        body: JSON.stringify({
          event_id: eventId,
          sequence_number: seq,
          prompt_content: prompt,
        }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Failed to create round";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderRoundsEditor(eventId);
      }
    });
  }

  async showPromptsModal(roundId, eventId, isDraft) {
    const res = await apiRequest(`/api/v1/rounds/${roundId}/prompts`);
    const prompts = res.ok ? res.data : [];

    let bodyHtml = `
      <div style="margin-bottom: 1rem;">
        <h4 style="font-size: var(--tv-text-sm); color: var(--tv-text-secondary);">Pinned Challenge Prompts</h4>
        ${
          prompts.length === 0
            ? `<p style="font-size: var(--tv-text-sm); color: var(--tv-text-muted);">No prompts pinned to this round.</p>`
            : prompts
                .map(
                  (p) => `
              <div style="background: var(--tv-color-surface); padding: 0.75rem; border-radius: var(--tv-radius-sm); border: 1px solid var(--tv-border-default); margin-bottom: 0.5rem;">
                <div style="display: flex; justify-content: space-between; font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-bottom: 0.25rem;">
                  <span>v${p.version_number} | Tokens: ${p.token_count}</span>
                  <span class="tv-table__cell--mono">${p.checksum_sha256.substring(0, 12)}...</span>
                </div>
                <div style="font-family: var(--tv-font-mono); font-size: var(--tv-text-xs); white-space: pre-wrap; color: var(--tv-text-primary); max-height: 120px; overflow-y: auto;">
                  ${escapeHtml(p.content)}
                </div>
              </div>
            `
                )
                .join("")
        }
      </div>
    `;

    if (isDraft) {
      bodyHtml += `
        <form id="form-pin-new-prompt" style="border-top: 1px solid var(--tv-border-default); padding-top: 1rem; margin-top: 1rem;">
          <div class="tv-form-group">
            <label class="tv-label">Pin New Challenge Prompt Text</label>
            <textarea class="tv-input" id="pin-prompt-text" rows="3" required minlength="5" placeholder="Enter updated prompt text..."></textarea>
          </div>
          <div id="pin-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem;">
            <button type="submit" class="tv-btn tv-btn--primary tv-btn--sm">Pin Prompt</button>
          </div>
        </form>
      `;
    }

    this.openModal({
      title: `Round Prompts Inspection`,
      body: bodyHtml,
      footer: `<button type="button" class="tv-btn tv-btn--outline tv-btn--sm" id="btn-close-modal">Close</button>`,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-pin-new-prompt")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const content = document.getElementById("pin-prompt-text").value.trim();
      const errBox = document.getElementById("pin-err");

      const pinRes = await apiRequest(`/api/v1/rounds/${roundId}/prompts`, {
        method: "POST",
        body: JSON.stringify({ round_id: roundId, event_id: eventId, content }),
      });

      if (!pinRes.ok) {
        errBox.textContent = pinRes.error || "Failed to pin prompt";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderRoundsEditor(eventId);
      }
    });
  }

  async renderRoster(eventId) {
    this.setTitle("Participant Roster & Check-In", "Identity verification status, readiness indicators, and audited status corrections.");

    const res = await apiRequest(`/api/v1/registrations/${eventId}/roster`);
    if (!res.ok) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--error">Failed to load roster: ${res.error}</div>`;
      return;
    }
    const roster = res.data;

    this.container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-4);">
        <div>
          <span class="tv-badge tv-badge--saved">Confirmed: ${roster.filter((r) => r.status === "confirmed" || r.status === "checked_in").length}</span>
          <span class="tv-badge tv-badge--official" style="margin-left: 0.5rem;">Checked In: ${roster.filter((r) => r.checked_in_at).length}</span>
          <span class="tv-badge tv-badge--provisional" style="margin-left: 0.5rem;">Ready: ${roster.filter((r) => r.is_ready).length}</span>
        </div>
        <input class="tv-input" id="search-roster" placeholder="Search participant by name/email..." style="max-width: 280px;">
      </div>

      <div class="tv-card">
        <div class="tv-card__body">
          <div class="tv-table-wrapper">
            <table class="tv-table" id="roster-table">
              <thead>
                <tr>
                  <th>Participant</th>
                  <th>Verification</th>
                  <th>Status</th>
                  <th>Checked In</th>
                  <th>Ready Signal</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                ${
                  roster.length === 0
                    ? `<tr><td colspan="6" style="text-align: center; color: var(--tv-text-muted);">No participants registered yet.</td></tr>`
                    : roster
                        .map(
                          (p) => `
                      <tr>
                        <td>
                          <strong>${escapeHtml(p.display_name)}</strong><br>
                          <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">${escapeHtml(p.email)}</span>
                        </td>
                        <td>
                          ${
                            p.is_verified
                              ? `<span class="tv-badge tv-badge--saved">Verified (${escapeHtml(p.institution_name || "Institutional")})</span>`
                              : `<span class="tv-badge tv-badge--unavailable">Unverified Claim</span>`
                          }
                        </td>
                        <td><span class="tv-badge ${this.getStatusBadgeClass(p.status)}">${p.status.toUpperCase()}</span></td>
                        <td>${p.checked_in_at ? new Date(p.checked_in_at).toLocaleTimeString() : "--"}</td>
                        <td>${p.is_ready ? `<span class="tv-badge tv-badge--saved">READY</span>` : `<span class="tv-badge tv-badge--unavailable">WAITING</span>`}</td>
                        <td>
                          <button class="tv-btn tv-btn--outline tv-btn--sm" data-correct-user="${p.user_id}" data-current-status="${p.status}">
                            Correct Status
                          </button>
                        </td>
                      </tr>
                    `
                        )
                        .join("")
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    document.getElementById("search-roster")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      document.querySelectorAll("#roster-table tbody tr").forEach((tr) => {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });

    this.container.querySelectorAll("[data-correct-user]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const userId = btn.getAttribute("data-correct-user");
        const currStatus = btn.getAttribute("data-current-status");
        this.showRosterCorrectionModal(eventId, userId, currStatus);
      });
    });
  }

  showRosterCorrectionModal(eventId, userId, currStatus) {
    this.openModal({
      title: "Manual Registration Correction",
      body: `
        <form id="form-roster-correction">
          <div class="tv-form-group">
            <label class="tv-label">Target Status</label>
            <select class="tv-input" id="roster-target-status">
              <option value="confirmed" ${currStatus === "confirmed" ? "selected" : ""}>Confirmed</option>
              <option value="checked_in" ${currStatus === "checked_in" ? "selected" : ""}>Checked In (Manual Override)</option>
              <option value="no_show" ${currStatus === "no_show" ? "selected" : ""}>No-Show</option>
              <option value="cancelled" ${currStatus === "cancelled" ? "selected" : ""}>Cancelled</option>
            </select>
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Mandatory Administrative Rationale</label>
            <textarea class="tv-input" id="roster-reason" rows="3" required placeholder="Explain why this status is being manually altered..."></textarea>
          </div>
          <div id="roster-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Commit Correction</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-roster-correction")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const target = document.getElementById("roster-target-status").value;
      const reason = document.getElementById("roster-reason").value.trim();
      const errBox = document.getElementById("roster-err");

      const res = await apiRequest(`/api/v1/registrations/${eventId}/roster/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ target_status: target, reason }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Correction rejected";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderRoster(eventId);
      }
    });
  }

  async renderLiveOperations(eventId) {
    this.setTitle("Live Operations & Incident Controls", "Real-time telemetry, server clock verification, and audited event-wide pause/void controls.");

    this.container.innerHTML = `<div class="tv-card"><p>Connecting to operational telemetry...</p></div>`;

    const fetchMetrics = async () => {
      const res = await apiRequest(`/api/v1/operations/events/${eventId}/live-metrics`);
      if (!res.ok) return null;
      return res.data;
    };

    const updateUI = (m) => {
      if (!m) return;
      this.container.innerHTML = `
        <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
          <div class="tv-card">
            <span class="tv-metric-item__label">Event Lifecycle State</span>
            <div class="tv-metric-item__value">
              <span class="tv-badge ${this.getStatusBadgeClass(m.event_status)}">${m.event_status.toUpperCase()}</span>
            </div>
            <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.5rem; display: block;">v${m.event_version} | ${m.is_paused ? `<strong style="color: var(--tv-status-error);">PAUSED (${m.total_pause_duration_seconds}s total)</strong>` : "RUNNING"}</span>
          </div>

          <div class="tv-card">
            <span class="tv-metric-item__label">Connected Client Sockets</span>
            <div class="tv-metric-item__value" style="color: var(--tv-color-accent);">${m.connected_sessions_count}</div>
            <span class="tv-badge tv-badge--saved" style="margin-top: 0.5rem;">Active Writers</span>
          </div>

          <div class="tv-card">
            <span class="tv-metric-item__label">Server Clock Health</span>
            <div class="tv-metric-item__value" style="font-size: var(--tv-text-base); font-family: var(--tv-font-mono);">
              ${m.server_time_ms} ms
            </div>
            <span class="tv-badge tv-badge--official" style="margin-top: 0.5rem;">Uncertainty &le; ${m.clock_uncertainty_ms}ms</span>
          </div>
        </div>

        <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
          <div class="tv-card">
            <span class="tv-metric-item__label">Durable ACK Latency (p95)</span>
            <div class="tv-metric-item__value" style="color: var(--tv-text-primary);">
              ${m.durable_ack_latency_p95_ms !== null ? `${m.durable_ack_latency_p95_ms} ms` : `<span class="tv-badge tv-badge--unavailable">Unavailable</span>`}
            </div>
            <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.5rem; display: block;">PostgreSQL Commit Wait</span>
          </div>

          <div class="tv-card">
            <span class="tv-metric-item__label">Transactional Outbox Lag</span>
            <div class="tv-metric-item__value" style="color: ${m.outbox_lag_count > 50 ? "var(--tv-status-error)" : "var(--tv-text-primary);"}">${m.outbox_lag_count}</div>
            <span class="tv-badge ${m.outbox_lag_count === 0 ? "tv-badge--saved" : "tv-badge--pending"}" style="margin-top: 0.5rem;">
              ${m.outbox_lag_count === 0 ? "Synchronized" : "Pending Dispatch"}
            </span>
          </div>

          <div class="tv-card">
            <span class="tv-metric-item__label">Platform Services</span>
            <div style="margin-top: 0.5rem; display: flex; gap: 0.5rem;">
              <span class="tv-badge ${m.postgres_healthy ? "tv-badge--official" : "tv-badge--error"}">PostgreSQL: ${m.postgres_healthy ? "OK" : "DOWN"}</span>
              <span class="tv-badge ${m.redis_healthy ? "tv-badge--official" : "tv-badge--error"}">Redis: ${m.redis_healthy ? "OK" : "DOWN"}</span>
            </div>
          </div>
        </div>

        <!-- Incident Controls Console -->
        <div class="tv-card tv-card--elevated">
          <div class="tv-card__header">
            <div>
              <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Live Incident Response Controls</h2>
              <p class="tv-card__subtitle">Event-wide uniform actions only. Individual deadline extensions are strictly prohibited.</p>
            </div>
            <span class="tv-badge tv-badge--provisional">Audited Gates</span>
          </div>
          <div class="tv-card__body">
            <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
              ${
                m.is_paused
                  ? `<button id="btn-resume-event" class="tv-btn tv-btn--primary">▶ Resume Event (Uniform Deadline Extension)</button>`
                  : `<button id="btn-pause-event" class="tv-btn tv-btn--outline" style="border-color: var(--tv-status-provisional); color: var(--tv-status-provisional);">⏸ Pause Event (Incident Freeze)</button>`
              }
              <button id="btn-void-round" class="tv-btn tv-btn--outline" style="border-color: var(--tv-status-error); color: var(--tv-status-error);">⛔ Void Round (Platform Disruption)</button>
            </div>
            ${
              m.incident_reason
                ? `<div class="tv-alert tv-alert--warning" style="margin-top: 1rem;">
                    <strong>Active Incident Rationale:</strong> ${escapeHtml(m.incident_reason)}
                  </div>`
                : ""
            }
          </div>
        </div>
      `;

      document.getElementById("btn-pause-event")?.addEventListener("click", () => this.showPauseModal(eventId, m.event_version));
      document.getElementById("btn-resume-event")?.addEventListener("click", () => this.showResumeModal(eventId, m.event_version));
      document.getElementById("btn-void-round")?.addEventListener("click", () => this.showVoidRoundModal(eventId, m.active_round_number));
    };

    const initial = await fetchMetrics();
    updateUI(initial);

    // Poll every 3 seconds for live dashboard updates
    this.pollTimer = setInterval(async () => {
      const updated = await fetchMetrics();
      updateUI(updated);
    }, 3000);
  }

  showPauseModal(eventId, expectedVersion) {
    this.openModal({
      title: "Pause Live Competition Event",
      body: `
        <div class="tv-alert tv-alert--warning">
          <div>
            <strong>Fairness Safeguard:</strong> Pausing an event uniformly freezes all round clocks.
            Upon resumption, all participant attempts receive an exact uniform deadline extension (&Delta;t).
          </div>
        </div>
        <form id="form-pause-event">
          <div class="tv-form-group">
            <label class="tv-label">Mandatory Incident Reason (Recorded in public audit log)</label>
            <textarea class="tv-input" id="pause-reason" rows="3" required placeholder="e.g. Venue power disruption affecting East wing participants..."></textarea>
          </div>
          <div id="pause-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Confirm Event Pause</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-pause-event")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const reason = document.getElementById("pause-reason").value.trim();
      const errBox = document.getElementById("pause-err");

      const res = await apiRequest(`/api/v1/events/${eventId}/pause`, {
        method: "POST",
        body: JSON.stringify({ expected_version: expectedVersion, reason }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Pause action rejected";
        errBox.style.display = "block";
      } else {
        this.closeModal();
      }
    });
  }

  showResumeModal(eventId, expectedVersion) {
    this.openModal({
      title: "Resume Paused Competition Event",
      body: `
        <p style="font-size: var(--tv-text-sm); color: var(--tv-text-secondary); margin-bottom: 1rem;">
          Resuming will compute the pause duration &Delta;t and automatically apply identical deadline extensions to all active participant attempts.
        </p>
        <form id="form-resume-event">
          <div class="tv-form-group">
            <label class="tv-label">Resumption Rationale</label>
            <input class="tv-input" id="resume-reason" required value="Technical issue resolved; resuming competition">
          </div>
          <div id="resume-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Resume All Participants</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-resume-event")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const reason = document.getElementById("resume-reason").value.trim();
      const errBox = document.getElementById("resume-err");

      const res = await apiRequest(`/api/v1/events/${eventId}/resume`, {
        method: "POST",
        body: JSON.stringify({ expected_version: expectedVersion, reason }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Resume action rejected";
        errBox.style.display = "block";
      } else {
        this.closeModal();
      }
    });
  }

  showVoidRoundModal(eventId, roundSeq) {
    this.openModal({
      title: "Void Competition Round",
      body: `
        <div class="tv-alert tv-alert--error">
          <div>
            <strong>Destructive Action:</strong> Voiding Round ${roundSeq || "current"} excludes it from composite scoring denominator for all participants. This action is permanently audited and requires platform admin authorization.
          </div>
        </div>
        <form id="form-void-round">
          <div class="tv-form-group">
            <label class="tv-label">Round UUID to Void</label>
            <input class="tv-input" id="void-round-id" required placeholder="Paste Round UUID">
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Optimistic Version</label>
            <input class="tv-input" id="void-expected-version" type="number" value="1" required>
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Incident Disruption Rationale</label>
            <textarea class="tv-input" id="void-reason" rows="3" required placeholder="Explain why round must be voided..."></textarea>
          </div>
          <div id="void-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary" style="background: var(--tv-status-error);">Confirm Void Round</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-void-round")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const rId = document.getElementById("void-round-id").value.trim();
      const ver = parseInt(document.getElementById("void-expected-version").value, 10);
      const reason = document.getElementById("void-reason").value.trim();
      const errBox = document.getElementById("void-err");

      const res = await apiRequest(`/api/v1/rounds/${rId}/void`, {
        method: "POST",
        body: JSON.stringify({ expected_version: ver, reason }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Void rejected";
        errBox.style.display = "block";
      } else {
        this.closeModal();
      }
    });
  }

  async renderJudging(eventId) {
    this.setTitle("Integrity Review & Judging Queue", "Evidence triage, documented anomaly signals, dual-approval sign-off, and appeals adjudication.");

    const res = await apiRequest(`/api/v1/integrity/events/${eventId}/cases`);
    if (!res.ok) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--error">Failed to load judging cases: ${res.error}</div>`;
      return;
    }
    const cases = res.data;

    this.container.innerHTML = `
      <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <span class="tv-metric-item__label">Pending Triage</span>
          <div class="tv-metric-item__value" style="color: var(--tv-status-provisional);">${cases.filter((c) => c.status === "flagged" || c.status === "investigating").length}</div>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Awaiting 2nd Approval</span>
          <div class="tv-metric-item__value" style="color: var(--tv-color-accent);">${cases.filter((c) => c.status === "pending_second_approval").length}</div>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Finalized Disqualifications</span>
          <div class="tv-metric-item__value" style="color: var(--tv-status-error);">${cases.filter((c) => c.status === "upheld").length}</div>
        </div>
      </div>

      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Integrity Flagged Cases</h2>
          <span class="tv-badge tv-badge--provisional">Dual-Approval Required for Upheld</span>
        </div>
        <div class="tv-card__body">
          ${
            cases.length === 0
              ? `<div style="text-align: center; padding: 2rem; color: var(--tv-text-muted);">No flagged integrity cases for this competition.</div>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr>
                        <th>Participant / Attempt</th>
                        <th>Trigger Reason</th>
                        <th>Status</th>
                        <th>1st Reviewer</th>
                        <th>2nd Reviewer</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${cases
                        .map(
                          (c) => `
                        <tr>
                          <td>
                            <span class="tv-table__cell--mono">${c.user_id.substring(0, 8)}...</span><br>
                            <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">Attempt: ${c.attempt_id.substring(0, 8)}</span>
                          </td>
                          <td><strong>${escapeHtml(c.trigger_reason)}</strong></td>
                          <td><span class="tv-badge ${this.getStatusBadgeClass(c.status)}">${c.status.toUpperCase()}</span></td>
                          <td>${c.assigned_reviewer_id ? `<span class="tv-table__cell--mono">${c.assigned_reviewer_id.substring(0, 8)}</span>` : "--"}</td>
                          <td>${c.second_reviewer_id ? `<span class="tv-table__cell--mono">${c.second_reviewer_id.substring(0, 8)}</span>` : "--"}</td>
                          <td>
                            ${
                              c.status === "flagged" || c.status === "investigating"
                                ? `<button class="tv-btn tv-btn--primary tv-btn--sm" data-judge-primary="${c.id}">Review Case</button>`
                                : c.status === "pending_second_approval"
                                ? `<button class="tv-btn tv-btn--outline tv-btn--sm" style="border-color: var(--tv-color-accent); color: var(--tv-color-accent);" data-judge-secondary="${c.id}">2nd Approval</button>`
                                : `<span class="tv-badge tv-badge--saved">RESOLVED</span>`
                            }
                          </td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    this.container.querySelectorAll("[data-judge-primary]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cId = btn.getAttribute("data-judge-primary");
        this.showPrimaryReviewModal(cId, eventId);
      });
    });

    this.container.querySelectorAll("[data-judge-secondary]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cId = btn.getAttribute("data-judge-secondary");
        this.showSecondApprovalModal(cId, eventId);
      });
    });
  }

  showPrimaryReviewModal(caseId, eventId) {
    this.openModal({
      title: "Primary Integrity Adjudication",
      body: `
        <form id="form-judge-primary">
          <div class="tv-form-group">
            <label class="tv-label">Finding Decision</label>
            <select class="tv-input" id="judge-decision">
              <option value="upheld">Upheld (Disqualification - requires 2nd judge confirmation)</option>
              <option value="dismissed">Dismissed (No integrity violation)</option>
            </select>
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Technical Rationale & Observations</label>
            <textarea class="tv-input" id="judge-rationale" rows="3" required placeholder="Evidence notes, keydown cadence analysis, diff inspection..."></textarea>
          </div>
          <div id="judge-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Record Finding</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-judge-primary")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const decision = document.getElementById("judge-decision").value;
      const rationale = document.getElementById("judge-rationale").value.trim();
      const errBox = document.getElementById("judge-err");

      const res = await apiRequest(`/api/v1/integrity/cases/${caseId}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          rationale,
          evidence_references: ["telemetry:latency_histogram", "keystrokes:cadence_spikes"],
        }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Adjudication failed";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderJudging(eventId);
      }
    });
  }

  showSecondApprovalModal(caseId, eventId) {
    this.openModal({
      title: "Secondary Judge Confirmation (Dual-Approval)",
      body: `
        <div class="tv-alert tv-alert--info">
          <div>
            <strong>Reviewer Separation Invariant:</strong> You must be an independent reviewer separate from the primary judge to confirm disqualifications.
          </div>
        </div>
        <form id="form-judge-second">
          <div class="tv-form-group">
            <label class="tv-label">Secondary Decision</label>
            <select class="tv-input" id="judge-second-decision">
              <option value="confirmed">Confirm Primary Disqualification</option>
              <option value="rejected">Reject Finding (Return to Review)</option>
            </select>
          </div>
          <div class="tv-form-group">
            <label class="tv-label">Secondary Independent Notes</label>
            <textarea class="tv-input" id="judge-second-notes" rows="3" required placeholder="Independent assessment notes..."></textarea>
          </div>
          <div id="judge-sec-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Commit Second Approval</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-judge-second")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const decision = document.getElementById("judge-second-decision").value;
      const notes = document.getElementById("judge-second-notes").value.trim();
      const errBox = document.getElementById("judge-sec-err");

      const res = await apiRequest(`/api/v1/integrity/cases/${caseId}/second-approve`, {
        method: "POST",
        body: JSON.stringify({ approval_decision: decision, second_notes: notes }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Second approval failed";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderJudging(eventId);
      }
    });
  }

  async renderResults(eventId) {
    this.setTitle("Results Preview, Approvals & Immutable Publication", "Calculated standings preview, tournament approval verification, immutable v1 publication, and audited amendments.");

    const [previewRes, historyRes] = await Promise.all([
      apiRequest(`/api/v1/results/events/${eventId}/preview`),
      apiRequest(`/api/v1/results/events/${eventId}/history`),
    ]);

    const preview = previewRes.ok ? previewRes.data : null;
    const history = historyRes.ok ? historyRes.data : [];

    this.container.innerHTML = `
      <!-- Publication Approval Policy Banner -->
      ${
        preview && !preview.can_publish
          ? `<div class="tv-alert tv-alert--warning" style="margin-bottom: var(--tv-space-4);">
              <div>
                <strong>Prize Policy Lock:</strong> ${escapeHtml(preview.block_reason || "Rule approval pending.")} Official results publication is blocked until tournament director approves the ruleset.
              </div>
            </div>`
          : ""
      }

      <!-- Top Action Bar -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-6);">
        <div>
          <span class="tv-badge ${history.length > 0 ? "tv-badge--official" : "tv-badge--pending"}">
            ${history.length > 0 ? `PUBLISHED (Current: v${history[0].version_number})` : "UNPUBLISHED DRAFT STANDINGS"}
          </span>
          ${preview ? `<span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-left: 0.5rem;">Digest: <code class="tv-table__cell--mono">${preview.signed_hash.substring(0, 16)}...</code></span>` : ""}
        </div>
        <div>
          ${
            history.length === 0
              ? `<button id="btn-publish-v1" class="tv-btn tv-btn--primary" ${preview && !preview.can_publish ? "disabled title='Prize approval required'" : ""}>
                  Publish Immutable Version 1
                </button>`
              : `<button id="btn-amend-results" class="tv-btn tv-btn--outline" style="border-color: var(--tv-color-accent); color: var(--tv-color-accent);">
                  + Publish Amended Version (v${history[0].version_number + 1})
                </button>`
          }
        </div>
      </div>

      <!-- Preview Standings Table -->
      <div class="tv-card" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Server-Compiled Participant Standings (${preview ? preview.total_participants : 0})</h2>
          <span class="tv-badge tv-badge--saved">arena-score-v1 Gated</span>
        </div>
        <div class="tv-card__body">
          ${
            !preview || preview.rankings.length === 0
              ? `<p style="text-align: center; color: var(--tv-text-muted); padding: 2rem;">No participant attempts compiled yet for this event.</p>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Participant</th>
                        <th>Net WPM</th>
                        <th>Gross WPM</th>
                        <th>Accuracy</th>
                        <th>Arena Score</th>
                        <th>Tier</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${preview.rankings
                        .map(
                          (r) => `
                        <tr>
                          <td><strong>#${r.rank_order}</strong></td>
                          <td>${escapeHtml(r.display_name)}</td>
                          <td class="tv-table__cell--mono">${r.net_wpm.toFixed(1)}</td>
                          <td class="tv-table__cell--mono">${r.gross_wpm.toFixed(1)}</td>
                          <td>${r.accuracy_pct.toFixed(1)}%</td>
                          <td><strong style="color: var(--tv-color-accent);">${r.arena_score}</strong></td>
                          <td><span class="tv-badge tv-badge--saved">${r.tier}</span></td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>

      <!-- Historical Publication Versions -->
      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Publication Version History & Audit Lineage</h2>
        </div>
        <div class="tv-card__body">
          ${
            history.length === 0
              ? `<p style="color: var(--tv-text-muted); font-size: var(--tv-text-sm);">No official versions published yet.</p>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr><th>Version</th><th>Published At</th><th>Signed Digest</th><th>Amendment Reason</th></tr>
                    </thead>
                    <tbody>
                      ${history
                        .map(
                          (h) => `
                        <tr>
                          <td><strong>v${h.version_number}</strong> ${h.is_current ? `<span class="tv-badge tv-badge--official" style="margin-left: 0.25rem;">CURRENT</span>` : ""}</td>
                          <td>${new Date(h.published_at).toLocaleString()}</td>
                          <td class="tv-table__cell--mono" style="font-size: var(--tv-text-xs);">${h.signed_hash}</td>
                          <td>${h.amendment_reason ? escapeHtml(h.amendment_reason) : "Initial Official Publication"}</td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    document.getElementById("btn-publish-v1")?.addEventListener("click", () => this.showPublishModal(eventId));
    document.getElementById("btn-amend-results")?.addEventListener("click", () => this.showAmendModal(eventId, history[0].version_number + 1));
  }

  showPublishModal(eventId) {
    this.openModal({
      title: "Publish Official Version 1 Standings",
      body: `
        <div class="tv-alert tv-alert--warning">
          <div>
            <strong>Permanently Immutable:</strong> Version 1 cannot be deleted or overwritten once published. Any future adjustments require an audited amendment (Version 2).
          </div>
        </div>
        <form id="form-publish-v1">
          <div class="tv-form-group">
            <label class="tv-label">Publication Note (Optional)</label>
            <input class="tv-input" id="pub-note" placeholder="e.g. Official finals standings verified by tournament director">
          </div>
          <div id="pub-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Commit Official Publication</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-publish-v1")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const note = document.getElementById("pub-note").value.trim();
      const errBox = document.getElementById("pub-err");

      const res = await apiRequest(`/api/v1/results/events/${eventId}/publish`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Publication failed";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderResults(eventId);
      }
    });
  }

  showAmendModal(eventId, nextVer) {
    this.openModal({
      title: `Publish Amended Results Version ${nextVer}`,
      body: `
        <div class="tv-alert tv-alert--info">
          <div>
            <strong>Amendment Audit Lineage:</strong> This action will create an append-only Version ${nextVer} linking the prior version. A mandatory justification rationale must be recorded.
          </div>
        </div>
        <form id="form-amend-results">
          <div class="tv-form-group">
            <label class="tv-label">Mandatory Amendment Reason (Appeals / Corrections)</label>
            <textarea class="tv-input" id="amend-reason" rows="3" required minlength="10" placeholder="e.g. Disqualification overturned on appeal by independent judge for participant #4..."></textarea>
          </div>
          <div id="amend-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
            <button type="button" class="tv-btn tv-btn--outline" id="btn-close-modal">Cancel</button>
            <button type="submit" class="tv-btn tv-btn--primary">Commit Amended Results</button>
          </div>
        </form>
      `,
    });

    document.getElementById("btn-close-modal")?.addEventListener("click", () => this.closeModal());
    document.getElementById("form-amend-results")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const reason = document.getElementById("amend-reason").value.trim();
      const errBox = document.getElementById("amend-err");

      const res = await apiRequest(`/api/v1/results/events/${eventId}/amend`, {
        method: "POST",
        body: JSON.stringify({ amendment_reason: reason }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Amendment failed";
        errBox.style.display = "block";
      } else {
        this.closeModal();
        this.renderResults(eventId);
      }
    });
  }

  async renderReports(eventId) {
    this.setTitle("Reports & Sanitized Data Exports", "Export event standings, full participant rosters, and audit trails. Protected against spreadsheet formula injection.");

    const res = await apiRequest(`/api/v1/exports/organization/${this.currentOrg.id}/jobs`);
    const jobs = res.ok ? res.data : [];

    this.container.innerHTML = `
      <div class="tv-grid-2" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Request New Data Export</h2>
          </div>
          <div class="tv-card__body">
            <form id="form-create-export">
              <div class="tv-form-group">
                <label class="tv-label">Export Dataset</label>
                <select class="tv-input" id="export-type">
                  <option value="event_standings">Official Event Standings (CSV)</option>
                  <option value="roster">Participant Roster & Verification (CSV)</option>
                  <option value="audit_trail">Security & Action Audit Log (CSV)</option>
                </select>
              </div>
              <p style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-bottom: 1rem;">
                CSV cells starting with <code>=</code>, <code>+</code>, <code>-</code>, or <code>@</code> are automatically escaped to prevent formula execution.
              </p>
              <div id="export-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
              <button type="submit" class="tv-btn tv-btn--primary tv-btn--sm">Generate Export Job</button>
            </form>
          </div>
        </div>

        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Security & Compliance Safeguards</h2>
          </div>
          <div class="tv-card__body" style="font-size: var(--tv-text-sm); color: var(--tv-text-secondary);">
            <ul style="padding-left: 1.25rem; display: flex; flex-direction: column; gap: 0.5rem;">
              <li>Export access is audited and restricted to authenticated organization administrators.</li>
              <li>Download tokens expire after single session or compliance window.</li>
              <li>Participant institutional identifiers are protected under tenant boundaries.</li>
            </ul>
          </div>
        </div>
      </div>

      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Recent Export Jobs</h2>
        </div>
        <div class="tv-card__body">
          ${
            jobs.length === 0
              ? `<p style="color: var(--tv-text-muted); font-size: var(--tv-text-sm); text-align: center; padding: 2rem;">No exports generated yet.</p>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr><th>Dataset</th><th>Status</th><th>Rows</th><th>Created</th><th>Download</th></tr>
                    </thead>
                    <tbody>
                      ${jobs
                        .map(
                          (j) => `
                        <tr>
                          <td><strong>${escapeHtml(j.export_type)}</strong></td>
                          <td><span class="tv-badge ${this.getStatusBadgeClass(j.status)}">${j.status.toUpperCase()}</span></td>
                          <td>${j.row_count}</td>
                          <td>${new Date(j.created_at).toLocaleString()}</td>
                          <td>
                            ${
                              j.status === "ready"
                                ? `<a href="/api/v1/exports/jobs/${j.id}/download" class="tv-btn tv-btn--outline tv-btn--sm" download>Download CSV</a>`
                                : `<span class="tv-badge tv-badge--unavailable">Processing</span>`
                            }
                          </td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    document.getElementById("form-create-export")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const exportType = document.getElementById("export-type").value;
      const errBox = document.getElementById("export-err");

      const res = await apiRequest("/api/v1/exports/jobs", {
        method: "POST",
        body: JSON.stringify({
          organization_id: this.currentOrg.id,
          export_type: exportType,
          event_id: eventId,
        }),
      });

      if (!res.ok) {
        errBox.textContent = res.error || "Export failed";
        errBox.style.display = "block";
      } else {
        this.renderReports(eventId);
      }
    });
  }

  async renderAuditTrail(eventId) {
    this.setTitle("Searchable Audit Trail", "Append-only security and operational action logs with automated secret redaction.");

    const res = await apiRequest(`/api/v1/audit/events?organization_id=${this.currentOrg.id}&target_id=${eventId}`);
    const logs = res.ok ? res.data : [];

    this.container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--tv-space-4);">
        <input class="tv-input" id="search-audit" placeholder="Filter by action or keyword..." style="max-width: 320px;">
        <span class="tv-badge tv-badge--saved">Tamper-Proof Append-Only</span>
      </div>

      <div class="tv-card">
        <div class="tv-card__body">
          ${
            logs.length === 0
              ? `<p style="text-align: center; color: var(--tv-text-muted); padding: 2rem;">No audit logs recorded for this event target.</p>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table" id="audit-table">
                    <thead>
                      <tr><th>Timestamp</th><th>Action Type</th><th>Actor</th><th>Payload / Changes</th></tr>
                    </thead>
                    <tbody>
                      ${logs
                        .map(
                          (l) => `
                        <tr>
                          <td style="white-space: nowrap;">${new Date(l.created_at).toLocaleString()}</td>
                          <td><strong>${escapeHtml(l.event_type)}</strong></td>
                          <td class="tv-table__cell--mono">${l.actor_user_id ? l.actor_user_id.substring(0, 8) : "SYSTEM"}</td>
                          <td>
                            <pre style="margin: 0; font-size: var(--tv-text-xs); color: var(--tv-text-secondary); max-height: 80px; overflow-y: auto;">${escapeHtml(JSON.stringify(l.payload_json, null, 2))}</pre>
                          </td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;

    document.getElementById("search-audit")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      document.querySelectorAll("#audit-table tbody tr").forEach((tr) => {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  async renderOrgMembers() {
    this.setTitle("Organization Members & Roles", `Role-based access control for ${this.currentOrg?.name || "tenant"}.`);

    const res = await apiRequest(`/api/v1/organizations/${this.currentOrg.id}/members/detail`);
    const members = res.ok ? res.data : [];

    this.container.innerHTML = `
      <div class="tv-grid-2" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Active Members (${members.length})</h2>
          </div>
          <div class="tv-card__body">
            <div class="tv-table-wrapper">
              <table class="tv-table">
                <thead>
                  <tr><th>Member</th><th>Role</th><th>Joined</th><th>Actions</th></tr>
                </thead>
                <tbody>
                  ${members
                    .map(
                      (m) => `
                    <tr>
                      <td>
                        <strong>${escapeHtml(m.display_name)}</strong><br>
                        <span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">${escapeHtml(m.email)}</span>
                      </td>
                      <td><span class="tv-badge ${m.role === "owner" ? "tv-badge--official" : "tv-badge--saved"}">${m.role.toUpperCase()}</span></td>
                      <td>${new Date(m.created_at).toLocaleDateString()}</td>
                      <td>
                        ${
                          m.role === "owner"
                            ? `<span style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">Tenant Owner</span>`
                            : `<button class="tv-btn tv-btn--outline tv-btn--sm" style="color: var(--tv-status-error); border-color: var(--tv-status-error);" data-remove-member="${m.user_id}">Remove</button>`
                        }
                      </td>
                    </tr>
                  `
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="tv-card">
          <div class="tv-card__header">
            <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Add / Assign Member</h2>
          </div>
          <div class="tv-card__body">
            <form id="form-add-member">
              <div class="tv-form-group">
                <label class="tv-label">User UUID</label>
                <input class="tv-input" id="new-member-uuid" required placeholder="User UUID">
              </div>
              <div class="tv-form-group">
                <label class="tv-label">Assigned Role</label>
                <select class="tv-input" id="new-member-role">
                  <option value="organizer">Organizer (Full Event & Live Controls)</option>
                  <option value="reviewer">Reviewer (Integrity Judging & Appeals)</option>
                  <option value="member">Member (Read-Only Organization Access)</option>
                </select>
              </div>
              <div id="member-err" style="color: var(--tv-status-error); font-size: var(--tv-text-xs); display: none;"></div>
              <button type="submit" class="tv-btn tv-btn--primary tv-btn--sm">Assign Role</button>
            </form>
          </div>
        </div>
      </div>
    `;

    document.getElementById("form-add-member")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const uId = document.getElementById("new-member-uuid").value.trim();
      const role = document.getElementById("new-member-role").value;
      const errBox = document.getElementById("member-err");

      const addRes = await apiRequest(`/api/v1/organizations/${this.currentOrg.id}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: uId, role }),
      });

      if (!addRes.ok) {
        errBox.textContent = addRes.error || "Failed to add member";
        errBox.style.display = "block";
      } else {
        this.renderOrgMembers();
      }
    });

    this.container.querySelectorAll("[data-remove-member]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const uId = btn.getAttribute("data-remove-member");
        if (!confirm("Are you sure you want to remove this member?")) return;

        const delRes = await apiRequest(`/api/v1/organizations/${this.currentOrg.id}/members/${uId}`, {
          method: "DELETE",
        });

        if (delRes.ok) {
          this.renderOrgMembers();
        } else {
          alert(`Failed to remove member: ${delRes.error}`);
        }
      });
    });
  }

  async renderPlatformHealth() {
    this.setTitle("Platform Operations & Infrastructure Health", "Real service probes, un-dispatched outbox queue, and database connectivity.");

    const res = await apiRequest("/api/v1/operations/platform-health");
    if (!res.ok) {
      this.container.innerHTML = `<div class="tv-alert tv-alert--error">Access denied or error loading platform health: ${res.error}</div>`;
      return;
    }
    const h = res.data;

    this.container.innerHTML = `
      <div class="tv-grid-3" style="margin-bottom: var(--tv-space-6);">
        <div class="tv-card">
          <span class="tv-metric-item__label">Authoritative PostgreSQL</span>
          <div class="tv-metric-item__value">
            <span class="tv-badge ${h.postgres_connected ? "tv-badge--official" : "tv-badge--error"}">
              ${h.postgres_connected ? "CONNECTED (READ/WRITE)" : "OFFLINE"}
            </span>
          </div>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Coordination Redis</span>
          <div class="tv-metric-item__value">
            <span class="tv-badge ${h.redis_connected ? "tv-badge--official" : "tv-badge--error"}">
              ${h.redis_connected ? "ACTIVE PUB/SUB" : "DISCONNECTED"}
            </span>
          </div>
        </div>
        <div class="tv-card">
          <span class="tv-metric-item__label">Un-dispatched Outbox Lag</span>
          <div class="tv-metric-item__value" style="color: var(--tv-color-accent);">${h.pending_outbox_events}</div>
        </div>
      </div>

      <div class="tv-card">
        <div class="tv-card__header">
          <h2 class="tv-card__title" style="font-size: var(--tv-text-base);">Recent Compliance Retention Sweeps</h2>
        </div>
        <div class="tv-card__body">
          ${
            h.recent_retention_jobs.length === 0
              ? `<p style="color: var(--tv-text-muted); font-size: var(--tv-text-sm);">No automated retention sweeps recorded yet.</p>`
              : `<div class="tv-table-wrapper">
                  <table class="tv-table">
                    <thead>
                      <tr><th>Job Type</th><th>Status</th><th>Records Affected</th><th>Started</th></tr>
                    </thead>
                    <tbody>
                      ${h.recent_retention_jobs
                        .map(
                          (j) => `
                        <tr>
                          <td>${escapeHtml(j.job_type)}</td>
                          <td><span class="tv-badge tv-badge--saved">${j.status.toUpperCase()}</span></td>
                          <td>${j.records_affected}</td>
                          <td>${new Date(j.started_at).toLocaleString()}</td>
                        </tr>
                      `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>
      </div>
    `;
  }

  // ==========================================
  // HELPERS & MODALS
  // ==========================================

  setTitle(title, lead) {
    if (this.pageTitle) this.pageTitle.textContent = title;
    if (this.pageLead) this.pageLead.textContent = lead;
  }

  getStatusBadgeClass(status) {
    switch (status) {
      case "draft":
        return "tv-badge--pending";
      case "published":
      case "registration_open":
      case "check_in_open":
      case "ready":
        return "tv-badge--official";
      case "live":
        return "tv-badge--saved";
      case "paused":
        return "tv-badge--provisional";
      case "completed":
      case "review":
      case "results_published":
      case "amended":
        return "tv-badge--official";
      case "voided":
      case "cancelled":
      case "no_show":
        return "tv-badge--error";
      default:
        return "tv-badge--unavailable";
    }
  }

  openModal({ title, body, footer }) {
    if (!this.modalContainer) return;
    this._lastFocusedElement = document.activeElement;

    this.modalContainer.innerHTML = `
      <div class="tv-modal-backdrop" id="modal-backdrop">
        <div class="tv-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
          <div class="tv-modal__header">
            <h3 class="tv-modal__title" id="modal-title">${escapeHtml(title)}</h3>
            <button type="button" class="tv-btn tv-btn--outline tv-btn--sm" id="modal-close-x" aria-label="Close modal">&times;</button>
          </div>
          <div class="tv-modal__body">
            ${body}
          </div>
          ${footer ? `<div class="tv-modal__footer">${footer}</div>` : ""}
        </div>
      </div>
    `;

    document.getElementById("modal-close-x")?.addEventListener("click", () => this.closeModal());
    document.getElementById("modal-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "modal-backdrop") {
        this.closeModal();
      }
    });

    // Keyboard accessibility: Escape key closes modal (WCAG 2.1.2)
    this._modalEscListener = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        this.closeModal();
      }
    };
    window.addEventListener("keydown", this._modalEscListener);

    // Initial focus placement (WCAG 2.4.3)
    const firstInteractive = this.modalContainer.querySelector("input, select, textarea, button:not(#modal-close-x)");
    if (firstInteractive && typeof firstInteractive.focus === "function") {
      firstInteractive.focus();
    } else {
      document.getElementById("modal-close-x")?.focus();
    }
  }

  closeModal() {
    if (this._modalEscListener) {
      window.removeEventListener("keydown", this._modalEscListener);
      this._modalEscListener = null;
    }
    if (this.modalContainer) {
      this.modalContainer.innerHTML = "";
    }
    // Restore focus to triggering control (WCAG 2.4.3)
    if (this._lastFocusedElement && typeof this._lastFocusedElement.focus === "function") {
      this._lastFocusedElement.focus();
      this._lastFocusedElement = null;
    }
  }
}

// Instantiate and initialize on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  const app = new CommandCenter();
  app.init();
});

