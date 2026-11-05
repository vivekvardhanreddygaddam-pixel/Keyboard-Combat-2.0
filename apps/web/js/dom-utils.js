/**
 * TypeVector Arena — DOM Utilities & Accessibility Helpers
 * Pure vanilla JavaScript with no framework dependencies.
 */

/**
 * Escapes unsafe characters for HTML rendering.
 * @param {string} str - Raw string
 * @returns {string} Sanitized string
 */
export function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export const escapeHtml = escapeHTML;

/**
 * Creates an element with optional classes, attributes, and text content.
 * @param {string} tag
 * @param {string|string[]} [classes]
 * @param {Record<string, string>} [attributes]
 * @param {string} [text]
 * @returns {HTMLElement}
 */
export function createElement(tag, classes, attributes = {}, text = "") {
  const el = document.createElement(tag);
  if (classes) {
    if (Array.isArray(classes)) {
      classes.forEach((c) => c && el.classList.add(c));
    } else {
      classes.split(" ").forEach((c) => c && el.classList.add(c));
    }
  }
  for (const [key, val] of Object.entries(attributes)) {
    el.setAttribute(key, val);
  }
  if (text) {
    el.textContent = text;
  }
  return el;
}

/**
 * Screen-reader accessible live announcement.
 * @param {string} message - Message to speak to screen readers
 * @param {"polite"|"assertive"} [priority="polite"]
 */
export function announceToScreenReader(message, priority = "polite") {
  let liveRegion = document.getElementById("tv-live-announcer");
  if (!liveRegion) {
    liveRegion = document.createElement("div");
    liveRegion.id = "tv-live-announcer";
    liveRegion.className = "tv-sr-only";
    liveRegion.style.position = "absolute";
    liveRegion.style.width = "1px";
    liveRegion.style.height = "1px";
    liveRegion.style.padding = "0";
    liveRegion.style.overflow = "hidden";
    liveRegion.style.clip = "rect(0, 0, 0, 0)";
    liveRegion.style.whiteSpace = "nowrap";
    liveRegion.style.border = "0";
    document.body.appendChild(liveRegion);
  }
  liveRegion.setAttribute("aria-live", priority);
  liveRegion.textContent = message;
}

/**
 * Displays a lightweight toast notification.
 * @param {string} message
 * @param {"info"|"success"|"warning"|"error"} [type="info"]
 * @param {number} [durationMs=4000]
 */
export function showToast(message, type = "info", durationMs = 4000) {
  let container = document.getElementById("tv-toast-container");
  if (!container) {
    container = createElement("div", "tv-toast-container", {
      id: "tv-toast-container",
      role: "status",
      "aria-live": "polite",
    });
    document.body.appendChild(container);
  }

  const toast = createElement("div", `tv-toast tv-toast--${type}`, {}, message);
  container.appendChild(toast);
  announceToScreenReader(message, "polite");

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 200ms ease-out";
    setTimeout(() => toast.remove(), 250);
  }, durationMs);
}

