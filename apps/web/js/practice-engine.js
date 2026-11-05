/**
 * TypeVector Arena — Interactive Practice Typing Engine
 * Pure vanilla JavaScript ES module with zero frameworks.
 *
 * Provides:
 * - 9 authentic typing modes
 * - Layout-shift protected character token surface
 * - High-performance class toggling without DOM reconstruction
 * - IME composition handling & paste policy enforcement
 * - Local preview metrics updating during typing
 * - Authoritative server evaluation & deterministic alignment diff review
 */

import { api } from "./api-client.js";
import { announceToScreenReader, showToast } from "./dom-utils.js";

export class PracticeEngine {
  constructor() {
    this.modes = [];
    this.currentMode = "common_words";
    this.prompts = [];
    this.currentPrompt = null;
    this.targetText = "";
    this.inputBuffer = "";
    this.startedAt = null;
    this.completedAt = null;
    this.timerInterval = null;
    this.metricsInterval = null;
    this.isComposing = false;
    this.isFinished = false;
    this.isSubmitting = false;
    this.remainingSeconds = 60;

    // DOM References
    this.typingBox = document.getElementById("practice-typing-box");
    this.offscreenInput = document.getElementById("practice-offscreen-input");
    this.blurOverlay = document.getElementById("practice-blur-overlay");
    this.metricWpm = document.getElementById("metric-wpm");
    this.metricAcc = document.getElementById("metric-acc");
    this.metricTime = document.getElementById("metric-time");
    this.metricBadge = document.getElementById("metric-badge");
    this.modeButtonsContainer = document.getElementById("practice-mode-selector");
    this.reviewSection = document.getElementById("practice-review-section");
    this.diffContainer = document.getElementById("diff-view-container");
    this.errorBreakdownContainer = document.getElementById("error-breakdown-container");
    this.suggestionsContainer = document.getElementById("suggestions-container");
    this.historyContainer = document.getElementById("practice-history-container");
  }

  async init() {
    this.setupEventListeners();
    await this.loadModes();
    await this.selectMode(this.currentMode);
    await this.loadHistory();
  }

  setupEventListeners() {
    if (!this.offscreenInput || !this.typingBox) return;

    // Focus handling
    this.typingBox.addEventListener("click", () => this.focusInput());
    if (this.blurOverlay) {
      this.blurOverlay.addEventListener("click", () => this.focusInput());
    }

    this.offscreenInput.addEventListener("focus", () => {
      if (this.blurOverlay) this.blurOverlay.style.display = "none";
    });

    this.offscreenInput.addEventListener("blur", () => {
      if (!this.isFinished && this.startedAt && this.blurOverlay) {
        this.blurOverlay.style.display = "flex";
      }
    });

    // Paste policy enforcement
    this.offscreenInput.addEventListener("paste", (e) => {
      e.preventDefault();
      showToast("Pasting is disabled during typing practice.", "warning");
      announceToScreenReader("Pasting is disabled.");
    });

    // IME composition events
    this.offscreenInput.addEventListener("compositionstart", () => {
      this.isComposing = true;
    });

    this.offscreenInput.addEventListener("compositionend", (e) => {
      this.isComposing = false;
      this.handleInput(e);
    });

    // Keystroke input
    this.offscreenInput.addEventListener("input", (e) => {
      if (this.isComposing) return;
      this.handleInput(e);
    });

    // Escape key restarts
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !this.isSubmitting) {
        this.restartCurrentPrompt();
      }
    });

    // Action buttons in review section
    const tryAgainBtn = document.getElementById("practice-try-again-btn");
    if (tryAgainBtn) {
      tryAgainBtn.addEventListener("click", () => this.restartCurrentPrompt());
    }

    const nextPromptBtn = document.getElementById("practice-next-prompt-btn");
    if (nextPromptBtn) {
      nextPromptBtn.addEventListener("click", () => this.selectNextPrompt());
    }
  }

  focusInput() {
    if (this.offscreenInput && !this.isFinished) {
      this.offscreenInput.focus();
      if (this.blurOverlay) this.blurOverlay.style.display = "none";
    }
  }

  async loadModes() {
    const res = await api.listPracticeModes();
    if (res.ok && res.data && res.data.length > 0) {
      this.modes = res.data;
    } else {
      // Offline fallback catalog
      this.modes = [
        { mode: "common_words", title: "Common Words", is_timed: false },
        { mode: "sentences", title: "Sentences & Punctuation", is_timed: false },
        { mode: "paragraphs", title: "Short & Long Paragraphs", is_timed: false },
        { mode: "precision", title: "Numbers & Symbols", is_timed: false },
        { mode: "code", title: "Code Snippets", is_timed: false },
        { mode: "speed_sprint", title: "Speed Sprint (60s)", is_timed: true, duration_seconds: 60 },
        { mode: "accuracy_challenge", title: "Accuracy Challenge", is_timed: false },
        { mode: "endurance", title: "Endurance", is_timed: false },
        { mode: "diagnostic", title: "Diagnostic", is_timed: false },
      ];
    }
    this.renderModeButtons();
  }

  renderModeButtons() {
    if (!this.modeButtonsContainer) return;

    this.modeButtonsContainer.innerHTML = this.modes
      .map(
        (m) => `
        <button type="button" 
                class="tv-btn ${m.mode === this.currentMode ? "tv-btn--primary" : "tv-btn--secondary"} tv-btn--sm"
                data-mode="${m.mode}"
                aria-pressed="${m.mode === this.currentMode ? "true" : "false"}">
          ${escapeHtml(m.title)}
        </button>
      `
      )
      .join("");

    this.modeButtonsContainer.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const mode = btn.getAttribute("data-mode");
        if (mode && mode !== this.currentMode) {
          await this.selectMode(mode);
        }
      });
    });
  }

  async selectMode(mode) {
    this.currentMode = mode;
    this.renderModeButtons();

    // Fetch prompts for selected mode
    const res = await api.listPracticePrompts(mode);
    if (res.ok && res.data && res.data.length > 0) {
      this.prompts = res.data;
      this.currentPrompt = this.prompts[0];
    } else {
      // Fallback prompt
      this.currentPrompt = {
        id: `local-${mode}`,
        title: `${mode.toUpperCase()} Exercise`,
        content: "The quick brown fox jumps over the lazy dog. Accuracy precedes velocity.",
        mode: mode,
      };
    }

    this.setupPrompt(this.currentPrompt);
  }

  selectNextPrompt() {
    if (!this.prompts || this.prompts.length === 0) return;
    const currentIndex = this.prompts.findIndex((p) => p.id === this.currentPrompt?.id);
    const nextIndex = (currentIndex + 1) % this.prompts.length;
    this.currentPrompt = this.prompts[nextIndex];
    this.setupPrompt(this.currentPrompt);
  }

  setupPrompt(prompt) {
    this.stopTimers();
    this.currentPrompt = prompt;
    this.targetText = prompt.content;
    this.inputBuffer = "";
    this.startedAt = null;
    this.completedAt = null;
    this.isFinished = false;
    this.isSubmitting = false;

    const modeSpec = this.modes.find((m) => m.mode === this.currentMode);
    this.remainingSeconds = (modeSpec && modeSpec.duration_seconds) || 60;

    if (this.offscreenInput) {
      this.offscreenInput.value = "";
      this.offscreenInput.removeAttribute("disabled");
    }

    if (this.blurOverlay) this.blurOverlay.style.display = "none";
    if (this.reviewSection) this.reviewSection.style.display = "none";

    // Reset metric indicators
    if (this.metricWpm) this.metricWpm.textContent = "0";
    if (this.metricAcc) this.metricAcc.textContent = "100%";
    if (this.metricTime) {
      this.metricTime.textContent = modeSpec && modeSpec.is_timed ? `0:${this.remainingSeconds.toString().padStart(2, "0")}` : "0:00";
    }
    if (this.metricBadge) {
      this.metricBadge.className = "tv-badge tv-badge--local";
      this.metricBadge.textContent = "LOCAL PREVIEW";
    }

    // Render tokenized characters (prevents layout shift during typing)
    this.renderTargetTokens();
    this.focusInput();
    announceToScreenReader(`Practice loaded: ${prompt.title}. Begin typing to start timer.`);
  }

  renderTargetTokens() {
    if (!this.typingBox) return;

    const chars = Array.from(this.targetText);
    const spans = chars.map((ch, idx) => {
      let displayChar = ch;
      if (ch === " ") displayChar = " ";
      else if (ch === "\n") displayChar = "\n";

      const cursorClass = idx === 0 ? " tv-char--cursor" : "";
      return `<span class="tv-char tv-char--pending${cursorClass}" id="char-${idx}">${escapeHtml(displayChar)}</span>`;
    });

    this.typingBox.innerHTML = spans.join("") + `<div id="extra-chars-container" style="display: inline;"></div>`;
  }

  handleInput(e) {
    if (this.isFinished || this.isSubmitting) return;

    const prevInput = this.inputBuffer;
    this.inputBuffer = this.offscreenInput ? this.offscreenInput.value : "";

    // First keypress starts timers
    if (!this.startedAt && this.inputBuffer.length > 0) {
      this.startedAt = new Date();
      this.startTimers();
      announceToScreenReader("Timer started.");
    }

    // Update character token classes incrementally
    this.updateTokenClasses(prevInput.length, this.inputBuffer.length);

    // Check completion condition
    const modeSpec = this.modes.find((m) => m.mode === this.currentMode);
    if (!modeSpec?.is_timed && this.inputBuffer.length >= this.targetText.length) {
      this.finishSession();
    }
  }

  updateTokenClasses(prevLen, currLen) {
    const target = this.targetText;
    const input = this.inputBuffer;

    // Update characters from min(prevLen, currLen) - 1 to currLen + 1
    const startIdx = Math.max(0, Math.min(prevLen, currLen) - 2);
    const endIdx = Math.min(target.length, Math.max(prevLen, currLen) + 2);

    for (let i = startIdx; i < endIdx; i++) {
      const el = document.getElementById(`char-${i}`);
      if (!el) continue;

      if (i < input.length) {
        const isCorrect = input[i] === target[i];
        el.className = `tv-char ${isCorrect ? "tv-char--correct" : "tv-char--incorrect"}`;
      } else if (i === input.length) {
        el.className = "tv-char tv-char--pending tv-char--cursor";
      } else {
        el.className = "tv-char tv-char--pending";
      }
    }

    // Handle extra characters typed beyond target length
    const extraContainer = document.getElementById("extra-chars-container");
    if (extraContainer) {
      if (input.length > target.length) {
        const extraChars = input.slice(target.length);
        extraContainer.innerHTML = Array.from(extraChars)
          .map((ch) => `<span class="tv-char tv-char--extra">${escapeHtml(ch)}</span>`)
          .join("");
      } else {
        extraContainer.innerHTML = "";
      }
    }

    // Ensure cursor is placed on next unattempted char if past end
    if (input.length < target.length) {
      const currentCursorEl = document.getElementById(`char-${input.length}`);
      if (currentCursorEl && !currentCursorEl.classList.contains("tv-char--cursor")) {
        currentCursorEl.classList.add("tv-char--cursor");
      }
    }
  }

  startTimers() {
    const modeSpec = this.modes.find((m) => m.mode === this.currentMode);
    const isTimed = modeSpec && modeSpec.is_timed;

    // 1-second clock
    this.timerInterval = window.setInterval(() => {
      if (!this.startedAt || this.isFinished) return;

      if (isTimed) {
        this.remainingSeconds -= 1;
        const mins = Math.floor(this.remainingSeconds / 60);
        const secs = this.remainingSeconds % 60;
        if (this.metricTime) {
          this.metricTime.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;
        }
        if (this.remainingSeconds <= 0) {
          this.finishSession();
        }
      } else {
        const elapsed = Math.floor((new Date() - this.startedAt) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        if (this.metricTime) {
          this.metricTime.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;
        }
      }
    }, 1000);

    // 250ms throttled local preview metrics
    this.metricsInterval = window.setInterval(() => {
      this.updateLocalPreviewMetrics();
    }, 250);
  }

  stopTimers() {
    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.metricsInterval) clearInterval(this.metricsInterval);
    this.timerInterval = null;
    this.metricsInterval = null;
  }

  updateLocalPreviewMetrics() {
    if (!this.startedAt || this.inputBuffer.length === 0) return;

    const durationSec = Math.max(0.5, (new Date() - this.startedAt) / 1000);
    const durationMin = durationSec / 60.0;

    let correct = 0;
    let errors = 0;
    const len = Math.min(this.inputBuffer.length, this.targetText.length);

    for (let i = 0; i < len; i++) {
      if (this.inputBuffer[i] === this.targetText[i]) {
        correct++;
      } else {
        errors++;
      }
    }

    // Local Net WPM preview: ((correct / 5) - errors) / minutes
    const netWords = Math.max(0, correct / 5.0 - errors);
    const netWpm = Math.round((netWords / durationMin) * 10) / 10;
    const accuracy = Math.round((correct / this.inputBuffer.length) * 100);

    if (this.metricWpm) this.metricWpm.textContent = netWpm.toString();
    if (this.metricAcc) this.metricAcc.textContent = `${accuracy}%`;
  }

  async finishSession() {
    if (this.isFinished) return;
    this.isFinished = true;
    this.completedAt = new Date();
    this.stopTimers();

    if (this.offscreenInput) {
      this.offscreenInput.setAttribute("disabled", "true");
    }

    if (this.metricBadge) {
      this.metricBadge.className = "tv-badge tv-badge--active";
      this.metricBadge.textContent = "EVALUATING (SERVER)...";
    }

    announceToScreenReader("Typing attempt complete. Submitting for authoritative server evaluation.");

    await this.submitSession();
  }

  async submitSession() {
    this.isSubmitting = true;

    const payload = {
      prompt_id: this.currentPrompt?.id,
      mode: this.currentMode,
      language: this.currentPrompt?.language || "en",
      target_text: this.targetText,
      input_text: this.inputBuffer,
      started_at: this.startedAt.toISOString(),
      completed_at: this.completedAt.toISOString(),
    };

    const res = await api.submitPracticeSession(payload);
    this.isSubmitting = false;

    if (res.ok && res.data) {
      this.renderEvaluationResults(res.data);
      if (this.metricBadge) {
        this.metricBadge.className = "tv-badge tv-badge--active";
        this.metricBadge.textContent = res.data.is_saved ? "SAVED (SERVER VERIFIED)" : "EVALUATED (SERVER STANDALONE)";
      }
      showToast(res.data.is_saved ? "Practice attempt evaluated and saved." : "Practice attempt evaluated authoritatively.", "success");
      await this.loadHistory();
    } else {
      // Local fallback display if backend is offline
      if (this.metricBadge) {
        this.metricBadge.className = "tv-badge tv-badge--local";
        this.metricBadge.textContent = "OFFLINE (LOCAL EVALUATION)";
      }
      showToast("Evaluation offline: calculated locally.", "warning");
      this.renderLocalFallbackResults();
    }
  }

  renderEvaluationResults(data) {
    if (!this.reviewSection) return;
    this.reviewSection.style.display = "block";

    const { metrics, segments, error_breakdown, suggestions } = data;

    // Update authoritative metrics
    if (this.metricWpm) this.metricWpm.textContent = metrics.net_wpm.toString();
    if (this.metricAcc) this.metricAcc.textContent = `${metrics.accuracy_pct}%`;
    if (this.metricTime) this.metricTime.textContent = `${metrics.duration_seconds}s`;

    // 1. Render Character Alignment Diff
    if (this.diffContainer && segments) {
      this.diffContainer.innerHTML = segments
        .map((seg) => {
          if (seg.type === "match") {
            return `<span class="tv-diff-token tv-diff-token--match">${escapeHtml(seg.expected || "")}</span>`;
          } else if (seg.type === "tail") {
            return `<span class="tv-diff-token tv-diff-token--tail" title="Unattempted tail">${escapeHtml(seg.expected || "")}</span>`;
          } else if (seg.category === "omission") {
            return `<span class="tv-diff-token tv-diff-token--del" title="Omitted character">${escapeHtml(seg.expected || "␣")}</span>`;
          } else if (seg.category === "insertion") {
            return `<span class="tv-diff-token tv-diff-token--ins" title="Extra character: ${escapeHtml(seg.actual || "")}">+${escapeHtml(seg.actual || "")}</span>`;
          } else {
            // Substitution / Case / Space error
            const tooltip = `Expected '${escapeHtml(seg.expected || "")}', typed '${escapeHtml(seg.actual || "")}'`;
            return `<span class="tv-diff-token tv-diff-token--sub" title="${tooltip}">${escapeHtml(seg.actual || "␣")}</span>`;
          }
        })
        .join("");
    }

    // 2. Render Mistake Breakdown Cards
    if (this.errorBreakdownContainer && error_breakdown) {
      this.errorBreakdownContainer.innerHTML = `
        <div class="tv-grid-3" style="gap: var(--tv-space-3);">
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Substitutions</span>
            <span class="tv-metric-item__value" style="color: #ef4444;">${error_breakdown.substitution || 0}</span>
          </div>
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Capitalization (Case)</span>
            <span class="tv-metric-item__value" style="color: #f59e0b;">${error_breakdown.case_error || 0}</span>
          </div>
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Spacing Mistakes</span>
            <span class="tv-metric-item__value" style="color: #0ea5e9;">${error_breakdown.space_error || 0}</span>
          </div>
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Punctuation</span>
            <span class="tv-metric-item__value">${error_breakdown.punctuation_error || 0}</span>
          </div>
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Numbers & Symbols</span>
            <span class="tv-metric-item__value">${error_breakdown.digit_symbol_error || 0}</span>
          </div>
          <div class="tv-card tv-card--elevated" style="padding: 1rem;">
            <span class="tv-metric-item__label">Omissions (Skipped)</span>
            <span class="tv-metric-item__value" style="color: #eab308;">${error_breakdown.omission || 0}</span>
          </div>
        </div>
      `;
    }

    // 3. Render Educational Recommendations
    if (this.suggestionsContainer && suggestions && suggestions.length > 0) {
      this.suggestionsContainer.innerHTML = `
        <ul style="list-style-type: none; padding-left: 0; margin-top: 0.5rem;">
          ${suggestions.map((s) => `
            <li style="padding: 0.5rem 0; border-bottom: 1px solid var(--tv-border-subtle); display: flex; gap: 0.5rem; align-items: flex-start;">
              <span style="color: var(--tv-color-accent);">→</span>
              <span>${escapeHtml(s)}</span>
            </li>
          `).join("")}
        </ul>
      `;
    }

    this.reviewSection.scrollIntoView({ behavior: "smooth", block: "start" });
    announceToScreenReader(`Evaluation complete. Net speed: ${metrics.net_wpm} Words Per Minute. Accuracy: ${metrics.accuracy_pct} percent.`);
  }

  renderLocalFallbackResults() {
    if (!this.reviewSection) return;
    this.reviewSection.style.display = "block";

    if (this.diffContainer) {
      const target = this.targetText;
      const input = this.inputBuffer;
      let html = "";
      const len = Math.max(target.length, input.length);
      for (let i = 0; i < len; i++) {
        const tChar = target[i];
        const iChar = input[i];
        if (i >= target.length) {
          html += `<span style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">${escapeHtml(iChar || " ")}</span>`;
        } else if (i >= input.length) {
          html += `<span style="color: var(--tv-text-muted); opacity: 0.5;">${escapeHtml(tChar)}</span>`;
        } else if (tChar === iChar) {
          html += `<span>${escapeHtml(tChar)}</span>`;
        } else {
          html += `<span style="background: rgba(239, 68, 68, 0.2); color: #f87171; text-decoration: underline;">${escapeHtml(iChar)}</span>`;
        }
      }
      this.diffContainer.innerHTML = html;
    }
    if (this.suggestionsContainer) {
      this.suggestionsContainer.innerHTML = `<p>Maintain steady typing cadence. Server analytics will activate when backend reconnects.</p>`;
    }
  }

  async loadHistory() {
    if (!this.historyContainer) return;

    const res = await api.getMyPracticeHistory(10, 0);
    if (res.ok && res.data && res.data.length > 0) {
      this.historyContainer.innerHTML = `
        <table class="tv-table" style="width: 100%; font-size: var(--tv-text-sm);">
          <thead>
            <tr>
              <th>Date</th>
              <th>Mode</th>
              <th>Net WPM</th>
              <th>Accuracy</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${res.data
              .map(
                (item) => `
              <tr>
                <td>${new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                <td><span class="tv-badge tv-badge--local">${escapeHtml(item.mode)}</span></td>
                <td style="font-weight: 700; color: var(--tv-color-accent);">${item.net_wpm}</td>
                <td>${item.accuracy_pct}%</td>
                <td><span class="tv-badge tv-badge--active">Saved</span></td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      `;
    } else {
      this.historyContainer.innerHTML = `
        <div class="tv-empty-state" style="padding: var(--tv-space-6);">
          <p class="tv-empty-state__title" style="font-size: var(--tv-text-base);">No Recent Saved Attempts</p>
          <p class="tv-empty-text" style="font-size: var(--tv-text-xs); color: var(--tv-text-muted);">
            Sign in to your participant account to automatically persist your practice progression history.
          </p>
        </div>
      `;
    }
  }

  restartCurrentPrompt() {
    if (this.currentPrompt) {
      this.setupPrompt(this.currentPrompt);
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

export function initPracticePage() {
  const engine = new PracticeEngine();
  window.__typevectorPracticeEngine = engine;
  engine.init();
  return engine;
}

