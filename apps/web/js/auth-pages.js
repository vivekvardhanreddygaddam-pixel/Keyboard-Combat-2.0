/**
 * TypeVector Arena — Authentication & Account Page Handlers
 * Pure vanilla JavaScript ES module with zero frameworks.
 */

import { api } from "./api-client.js";
import { announceToScreenReader, showToast } from "./dom-utils.js";

/**
 * Initializes the Login Form on /login/
 */
export function initLoginForm() {
  const form = document.getElementById("login-form");
  const submitBtn = document.getElementById("login-submit-btn");
  const feedbackEl = document.getElementById("login-feedback");

  if (!form || !submitBtn) return;

  submitBtn.removeAttribute("disabled");
  submitBtn.removeAttribute("title");
  submitBtn.textContent = "Sign In";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("login-email")?.value?.trim();
    const password = document.getElementById("login-password")?.value;

    if (!email || !password) {
      if (feedbackEl) {
        feedbackEl.className = "tv-alert tv-alert--danger";
        feedbackEl.textContent = "Please enter both email and password.";
        feedbackEl.style.display = "block";
      }
      return;
    }

    submitBtn.setAttribute("disabled", "true");
    submitBtn.textContent = "Signing In...";

    const res = await api.login(email, password);
    submitBtn.removeAttribute("disabled");
    submitBtn.textContent = "Sign In";

    if (!res.ok) {
      const msg = res.error || "Authentication failed. Please verify credentials.";
      if (feedbackEl) {
        feedbackEl.className = "tv-alert tv-alert--danger";
        feedbackEl.textContent = msg;
        feedbackEl.style.display = "block";
      }
      announceToScreenReader(msg);
      showToast(msg, "error");
      return;
    }

    showToast("Signed in successfully. Redirecting...", "success");
    announceToScreenReader("Signed in successfully.");
    window.location.href = "/account/";
  });
}

/**
 * Initializes the Registration Form on /register/
 */
export function initRegisterForm() {
  const form = document.getElementById("register-form");
  const submitBtn = document.getElementById("register-submit-btn");
  const feedbackEl = document.getElementById("register-feedback");

  if (!form || !submitBtn) return;

  submitBtn.removeAttribute("disabled");
  submitBtn.removeAttribute("title");
  submitBtn.textContent = "Create Account";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("reg-email")?.value?.trim();
    const displayName = (document.getElementById("reg-name") || document.getElementById("reg-username"))?.value?.trim();
    const password = document.getElementById("reg-password")?.value;
    const confirmInput = document.getElementById("reg-confirm");
    const confirm = confirmInput ? confirmInput.value : password;

    if (!email || !displayName || !password) {
      if (feedbackEl) {
        feedbackEl.className = "tv-alert tv-alert--danger";
        feedbackEl.textContent = "All fields are required.";
        feedbackEl.style.display = "block";
      }
      return;
    }

    if (password !== confirm) {
      if (feedbackEl) {
        feedbackEl.className = "tv-alert tv-alert--danger";
        feedbackEl.textContent = "Passwords do not match.";
        feedbackEl.style.display = "block";
      }
      return;
    }

    submitBtn.setAttribute("disabled", "true");
    submitBtn.textContent = "Creating Account...";

    const res = await api.register(email, password, displayName);
    submitBtn.removeAttribute("disabled");
    submitBtn.textContent = "Create Account";

    if (!res.ok) {
      const msg = res.error || "Registration failed.";
      if (feedbackEl) {
        feedbackEl.className = "tv-alert tv-alert--danger";
        feedbackEl.textContent = msg;
        feedbackEl.style.display = "block";
      }
      showToast(msg, "error");
      return;
    }

    // Auto-login after registration
    const loginRes = await api.login(email, password);
    if (loginRes.ok) {
      showToast("Account created! Redirecting to account...", "success");
      window.location.href = "/account/";
    } else {
      window.location.href = "/login/";
    }
  });
}

/**
 * Initializes the Participant Account page on /account/
 */
export async function initAccountPage() {
  const profileContainer = document.getElementById("account-profile-container");
  const claimsList = document.getElementById("account-claims-list");
  const registrationsList = document.getElementById("account-registrations-list");
  const logoutBtn = document.getElementById("account-logout-btn");

  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      await api.logout();
      window.location.href = "/login/";
    });
  }

  // Load profile
  const meRes = await api.getMe();
  if (!meRes.ok) {
    if (profileContainer) {
      profileContainer.innerHTML = `
        <div class="tv-alert tv-alert--warning">
          <strong>Not Signed In:</strong> You are currently viewing the account shell anonymously.
          <a href="/login/" class="tv-btn tv-btn--sm tv-btn--primary" style="margin-left: 1rem;">Sign In</a>
        </div>
      `;
    }
    return;
  }

  const { user, claims } = meRes.data;

  if (profileContainer) {
    profileContainer.innerHTML = `
      <div class="tv-card">
        <div class="tv-card__header">
          <div>
            <h2 class="tv-card__title">${escapeHtml(user.display_name)}</h2>
            <p class="tv-card__subtitle">${escapeHtml(user.email)} • Role: <span class="tv-badge tv-badge--active">${escapeHtml(user.role)}</span></p>
          </div>
        </div>
        <div class="tv-card__body">
          <p style="font-size: var(--tv-text-sm); color: var(--tv-text-muted);">
            Member since: ${new Date(user.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    `;
  }

  // Render claims
  if (claimsList) {
    if (!claims || claims.length === 0) {
      claimsList.innerHTML = `
        <div class="tv-empty-state">
          <p class="tv-empty-state__title">No Verified Identity Claims</p>
          <p class="tv-empty-state__description">Submit an institutional ID or roll number to qualify for restricted tournaments.</p>
        </div>
      `;
    } else {
      claimsList.innerHTML = claims.map(c => `
        <div class="tv-card" style="margin-bottom: 0.5rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <strong>${escapeHtml(c.claim_type)}:</strong> <code>${escapeHtml(c.claim_value)}</code>
            </div>
            <span class="tv-badge tv-badge--${c.status === 'verified' ? 'active' : 'pending'}">${escapeHtml(c.status)}</span>
          </div>
          ${c.evidence_notes ? `<p style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.25rem;">${escapeHtml(c.evidence_notes)}</p>` : ""}
        </div>
      `).join("");
    }
  }

  // Load registrations
  if (registrationsList) {
    const regRes = await api.getMyRegistrations();
    if (regRes.ok && regRes.data && regRes.data.length > 0) {
      registrationsList.innerHTML = regRes.data.map(r => `
        <div class="tv-card" style="margin-bottom: 0.5rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <strong>Event:</strong> <code>${escapeHtml(r.event_id)}</code>
            </div>
            <span class="tv-badge tv-badge--${r.status === 'confirmed' ? 'active' : 'neutral'}">${escapeHtml(r.status)}</span>
          </div>
          <p style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-top: 0.25rem;">
            Registered: ${new Date(r.registered_at).toLocaleString()}
          </p>
        </div>
      `).join("");
    } else {
      registrationsList.innerHTML = `
        <div class="tv-empty-state">
          <p class="tv-empty-state__title">No Active Registrations</p>
          <p class="tv-empty-state__description">Browse published events and register to participate.</p>
        </div>
      `;
    }
  }

  // Load curriculum progress
  const curriculumContainer = document.getElementById("account-curriculum-container");
  if (curriculumContainer) {
    const progRes = await api.getMyCurriculumProgress();
    if (progRes.ok && progRes.data && progRes.data.length > 0) {
      curriculumContainer.innerHTML = `
        <div class="tv-grid-3" style="gap: 1rem;">
          ${progRes.data.map(p => `
            <div class="tv-card tv-card--elevated" style="padding: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                <strong>${escapeHtml(p.track_title)}</strong>
                <span class="tv-badge tv-badge--saved">Lvl ${p.current_level_number}</span>
              </div>
              <p style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">
                ${escapeHtml(p.current_level_title)} • ${p.qualifying_attempts_count}/${p.pass_attempts_required} passes
              </p>
            </div>
          `).join("")}
        </div>
      `;
    } else {
      curriculumContainer.innerHTML = `
        <p style="color: var(--tv-text-muted); font-size: var(--tv-text-sm);">
          No track progression recorded yet. Complete assessments in Practice Mode to unlock levels.
        </p>
      `;
    }
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
