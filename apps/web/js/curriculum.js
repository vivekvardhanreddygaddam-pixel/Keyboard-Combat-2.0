/**
 * TypeVector Arena — Curriculum & Progression View
 * Pure vanilla JavaScript ES module with zero frameworks.
 *
 * Implements:
 * - 7 independent skill tracks
 * - Multi-attempt qualification progress tracking
 * - Evidence-backed adaptive recommendations
 * - Transparent level criteria breakdown
 */

import { api } from "./api-client.js";
import { announceToScreenReader } from "./dom-utils.js";

export async function initCurriculumView(containerId = "curriculum-dashboard-container", onSelectLevelPrompt = null) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div class="tv-empty-state" style="padding: 2rem;">
      <p style="color: var(--tv-text-muted);">Loading skill tracks and qualification progress...</p>
    </div>
  `;

  // 1. Fetch Tracks, User Progress, and Adaptive Recommendations in parallel
  const [tracksRes, progressRes, recRes] = await Promise.all([
    api.listCurriculumTracks(),
    api.getMyCurriculumProgress(),
    api.getAdaptiveRecommendation(),
  ]);

  const tracks = (tracksRes.ok && tracksRes.data) || getFallbackTracks();
  const progressMap = {};
  if (progressRes.ok && progressRes.data) {
    progressRes.data.forEach((p) => {
      progressMap[p.track_slug] = p;
    });
  }

  // 2. Render HTML View
  let html = "";

  // A. Adaptive Recommendation Card (if authenticated and available)
  if (recRes.ok && recRes.data) {
    const rec = recRes.data;
    html += `
      <div class="tv-card tv-card--elevated" style="margin-bottom: var(--tv-space-6); border-left: 4px solid var(--tv-color-accent);">
        <div class="tv-card__header" style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
          <div>
            <span class="tv-badge tv-badge--local" style="margin-bottom: 0.25rem;">EVIDENCE-BASED ADAPTIVE TARGET</span>
            <h2 class="tv-card__title" style="margin-top: 0.25rem;">Recommended: ${escapeHtml(rec.recommended_track_title)} (Level ${rec.recommended_level})</h2>
            <p class="tv-card__subtitle">${escapeHtml(rec.reason)}</p>
          </div>
          <span class="tv-badge tv-badge--neutral">Confidence: ${escapeHtml(rec.confidence)}</span>
        </div>
        <div class="tv-card__body">
          <p style="font-size: var(--tv-text-sm); color: var(--tv-text-secondary); margin-bottom: 0.75rem;">
            <strong>Recorded Evidence:</strong> ${escapeHtml(rec.evidence)}
          </p>
          <div style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); padding: 0.5rem; background: rgba(255, 255, 255, 0.03); border-radius: 4px;">
            ℹ️ ${escapeHtml(rec.disclaimer)}
          </div>
        </div>
      </div>
    `;
  }

  // B. Tracks Grid
  html += `
    <div style="margin-bottom: var(--tv-space-4); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
      <div>
        <h2 style="font-size: var(--tv-text-xl); font-weight: 700;">Independent Skill Tracks</h2>
        <p style="font-size: var(--tv-text-sm); color: var(--tv-text-muted);">
          Each track progresses independently based on multi-attempt qualification evidence.
        </p>
      </div>
      <span class="tv-badge tv-badge--local">Criteria: Draft 2026.1-draft</span>
    </div>

    <div class="tv-grid-3" style="gap: var(--tv-space-4);">
  `;

  tracks.forEach((track) => {
    const prog = progressMap[track.slug] || {
      current_level_number: 1,
      current_level_title: "Foundation",
      qualifying_attempts_count: 0,
      pass_attempts_required: 3,
      is_track_completed: false,
    };

    const levelNum = prog.current_level_number;
    const levelTitle = prog.current_level_title;
    const passes = prog.qualifying_attempts_count;
    const req = prog.pass_attempts_required;
    const pct = Math.min(100, Math.round((passes / Math.max(1, req)) * 100));

    html += `
      <div class="tv-card tv-card--interactive" style="display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
            <h3 style="font-size: var(--tv-text-base); font-weight: 700; color: var(--tv-text-primary);">${escapeHtml(track.title)}</h3>
            <span class="tv-badge ${prog.is_track_completed ? "tv-badge--active" : "tv-badge--saved"}">
              Level ${levelNum}: ${escapeHtml(levelTitle)}
            </span>
          </div>
          <p style="font-size: var(--tv-text-xs); color: var(--tv-text-muted); margin-bottom: 1rem; min-height: 2.5rem;">
            ${escapeHtml(track.description || "")}
          </p>

          <!-- Multi-attempt Progress Bar -->
          <div style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 0.25rem;">
              <span>Qualifying Attempts</span>
              <strong>${passes} / ${req} ${prog.is_track_completed ? "★ Mastered" : ""}</strong>
            </div>
            <div style="height: 6px; background-color: var(--tv-color-surface-sunken); border-radius: 3px; overflow: hidden; border: 1px solid var(--tv-border-default);">
              <div style="height: 100%; width: ${pct}%; background-color: var(--tv-color-accent); transition: width 0.3s ease;"></div>
            </div>
          </div>
        </div>

        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
          <button type="button" 
                  class="tv-btn tv-btn--primary tv-btn--sm" 
                  style="flex: 1;"
                  data-track-slug="${track.slug}"
                  data-track-level="${levelNum}">
            Start Level ${levelNum}
          </button>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;

  // Bind Start Level buttons
  container.querySelectorAll("button[data-track-slug]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const slug = btn.getAttribute("data-track-slug");
      const lvl = parseInt(btn.getAttribute("data-track-level") || "1", 10);
      if (onSelectLevelPrompt) {
        onSelectLevelPrompt(slug, lvl);
      } else {
        // Fetch track detail and load prompt
        const trackDetailRes = await api.getCurriculumTrackDetail(slug);
        if (trackDetailRes.ok && trackDetailRes.data && trackDetailRes.data.levels) {
          const levelData = trackDetailRes.data.levels.find((l) => l.level_number === lvl);
          if (levelData) {
            announceToScreenReader(`Selected ${trackDetailRes.data.title} Level ${lvl}: ${levelData.title}`);
            // If on practice page, trigger practice engine setup
            const engineInstance = window.__typevectorPracticeEngine;
            if (engineInstance) {
              engineInstance.setupPrompt({
                id: `curriculum-${slug}-${lvl}`,
                mode: slug === "code-typing" ? "code" : "sentences",
                title: `${trackDetailRes.data.title} Level ${lvl} (${levelData.title})`,
                content: levelData.prompt_content,
                language: slug === "code-typing" ? "code" : "en",
              });
              const typingBox = document.getElementById("practice-typing-box");
              if (typingBox) typingBox.scrollIntoView({ behavior: "smooth" });
            }
          }
        }
      }
    });
  });
}

function getFallbackTracks() {
  return [
    { slug: "keyboard-fundamentals", title: "Keyboard Fundamentals", description: "Master home-row posture, key reaches, and finger recovery." },
    { slug: "word-accuracy", title: "Word Accuracy", description: "Eliminate hesitation on high-frequency vocabulary and tricky letter clusters." },
    { slug: "sentence-fluency", title: "Sentence Fluency", description: "Develop natural punctuation timing, capitalization cadence, and smooth phrasing." },
    { slug: "paragraph-fluency", title: "Paragraph Fluency", description: "Sustain speed and mental focus across multi-sentence paragraphs." },
    { slug: "precision-typing", title: "Precision Typing", description: "Master top-row number reaches, math symbols, currency codes, and structural brackets." },
    { slug: "code-typing", title: "Code Typing", description: "Type programming keywords, CamelCase, syntax brackets, and indentation with zero mistakes." },
    { slug: "speed-endurance", title: "Speed & Endurance", description: "Sustain high-velocity rhythm, fatigue resistance, and focus across extended sprints." },
  ];
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

