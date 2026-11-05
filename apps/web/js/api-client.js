/**
 * TypeVector Arena — Client API Fetch Wrapper
 * Pure vanilla JavaScript ES module with cookie session support and CSRF protection.
 */

const API_BASE = "http://127.0.0.1:8000";

let storedCsrfToken = "";

export function setCsrfToken(token) {
  storedCsrfToken = token || "";
}

export function getCsrfToken() {
  return storedCsrfToken;
}

/**
 * Executes an HTTP request against the TypeVector Arena backend.
 * @param {string} endpoint - API path (e.g., "/healthz" or "/api/v1/identity/me")
 * @param {RequestInit} [options] - Fetch options
 * @returns {Promise<{ ok: boolean, status: number, data: any, error?: string, code?: string }>}
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const method = (options.method || "GET").toUpperCase();

  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  // Attach CSRF token on mutating requests if present
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && storedCsrfToken) {
    headers["X-CSRF-Token"] = storedCsrfToken;
  }

  try {
    const response = await fetch(url, {
      ...options,
      method,
      credentials: "include", // Send and receive HttpOnly session cookies
      headers,
    });

    let data = null;
    const contentType = response.headers.get("content-type");
    if (contentType && (contentType.includes("json") || contentType.includes("problem+json"))) {
      data = await response.json().catch(() => null);
    } else {
      data = await response.text().catch(() => null);
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        data,
        error: (data && data.detail) || `HTTP Error ${response.status}`,
        code: (data && data.code) || `HTTP_${response.status}`,
      };
    }

    return {
      ok: true,
      status: response.status,
      data,
    };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: err instanceof Error ? err.message : "Network error / Service offline",
      code: "NETWORK_ERROR",
    };
  }
}

// High-level API convenience functions
export const api = {
  // Identity & Auth
  async register(email, password, displayName) {
    return apiRequest("/api/v1/identity/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
  },

  async login(email, password) {
    const res = await apiRequest("/api/v1/identity/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (res.ok && res.data && res.data.csrf_token) {
      setCsrfToken(res.data.csrf_token);
    }
    return res;
  },

  async logout() {
    const res = await apiRequest("/api/v1/identity/logout", { method: "POST" });
    setCsrfToken("");
    return res;
  },

  async getMe() {
    const res = await apiRequest("/api/v1/identity/me");
    if (res.ok && res.data && res.data.csrf_token) {
      setCsrfToken(res.data.csrf_token);
    }
    return res;
  },

  async submitClaim(claimType, claimValue, organizationId = null) {
    return apiRequest("/api/v1/identity/claims", {
      method: "POST",
      body: JSON.stringify({
        claim_type: claimType,
        claim_value: claimValue,
        organization_id: organizationId,
      }),
    });
  },

  async getMyClaims() {
    return apiRequest("/api/v1/identity/claims/my");
  },

  // Events & Registration
  async listEvents() {
    return apiRequest("/api/v1/events");
  },

  async getEvent(eventId) {
    return apiRequest(`/api/v1/events/${eventId}`);
  },

  async getEventCapacity(eventId) {
    return apiRequest(`/api/v1/registrations/${eventId}/capacity`);
  },

  async registerForEvent(eventId) {
    return apiRequest(`/api/v1/registrations/${eventId}`, { method: "POST" });
  },

  async cancelRegistration(eventId) {
    return apiRequest(`/api/v1/registrations/${eventId}`, { method: "DELETE" });
  },

  async getMyRegistrations() {
    return apiRequest("/api/v1/registrations/my");
  },

  // Practice Domain
  async listPracticeModes() {
    return apiRequest("/api/v1/practice/modes");
  },

  async listPracticePrompts(mode = null) {
    const endpoint = mode ? `/api/v1/practice/prompts?mode=${encodeURIComponent(mode)}` : "/api/v1/practice/prompts";
    return apiRequest(endpoint);
  },

  async getPracticePrompt(promptId) {
    return apiRequest(`/api/v1/practice/prompts/${encodeURIComponent(promptId)}`);
  },

  async submitPracticeSession(payload) {
    return apiRequest("/api/v1/practice/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getPracticeSession(sessionId) {
    return apiRequest(`/api/v1/practice/sessions/${encodeURIComponent(sessionId)}`);
  },

  async getMyPracticeHistory(limit = 20, offset = 0) {
    return apiRequest(`/api/v1/practice/history?limit=${limit}&offset=${offset}`);
  },

  // Curriculum Domain
  async listCurriculumTracks() {
    return apiRequest("/api/v1/curriculum/tracks");
  },

  async getCurriculumTrackDetail(slug) {
    return apiRequest(`/api/v1/curriculum/tracks/${encodeURIComponent(slug)}`);
  },

  async getMyCurriculumProgress() {
    return apiRequest("/api/v1/curriculum/progress");
  },

  async submitCurriculumAssessment(payload) {
    return apiRequest("/api/v1/curriculum/assessments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getAdaptiveRecommendation() {
    return apiRequest("/api/v1/curriculum/recommendations");
  },
};
