/**
 * TypeVector Arena — Shared Application Bootstrap
 * Bootstraps common layout behaviors, navigation states, and global accessibility.
 */

import { syncActiveNavLinks } from "./router.js";
import { announceToScreenReader } from "./dom-utils.js";

export function initApp() {
  // Sync active navigation link highlighting
  syncActiveNavLinks();

  // Escape key closes modals or toasts
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const toasts = document.querySelectorAll(".tv-toast");
      toasts.forEach((t) => t.remove());
    }
  });

  // Announce page title to screen reader on initial load
  const pageHeading = document.querySelector("h1");
  if (pageHeading && pageHeading.textContent) {
    announceToScreenReader(`Navigated to ${pageHeading.textContent.trim()}`);
  }
}

// Auto-run if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

