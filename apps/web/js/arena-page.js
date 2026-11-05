/**
 * TypeVector Arena — Arena Page Controller (apps/web/js/arena-page.js)
 */

import { ArenaWebSocketClient } from './arena-client.js';

export function initArenaPage() {
  const wsStatusEl = document.getElementById('ws-status');
  const ackWatermarkEl = document.getElementById('ack-watermark');
  const pendingQueueEl = document.getElementById('pending-queue');
  const committedCharsEl = document.getElementById('committed-chars');
  const workspaceEl = document.getElementById('arena-workspace');

  // Check URL params for attemptId or fallback
  const urlParams = new URLSearchParams(window.location.search);
  const attemptId = urlParams.get('attemptId');

  if (!attemptId) {
    if (workspaceEl) {
      workspaceEl.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
          <div style="font-size: 2rem; margin-bottom: 1rem;">🛡️</div>
          <h2 style="font-size: var(--tv-text-xl); font-weight: 700; margin-bottom: 0.5rem;">Single-Ranked-Round Core Active</h2>
          <p style="color: var(--tv-text-muted); max-width: 55ch; margin: 0 auto 1.5rem;">
            The <code>arena-ws-v1</code> WebSocket protocol, monotonic sequence engine, and writer-generation fencing are fully live. To join a live attempt, supply a valid <code>?attemptId=&lt;uuid&gt;</code> parameter or launch from your registered event lobby.
          </p>
          <div class="tv-alert tv-alert--info" style="max-width: 50ch; margin: 0 auto 1.5rem; text-align: left;">
            <strong>Durability Model:</strong> Keystrokes are buffered locally in memory until committed to PostgreSQL. If this browser tab crashes before receiving a Server ACK, unacknowledged keystrokes will be lost.
          </div>
          <a href="/events/" class="tv-btn tv-btn--primary">Browse Registered Events</a>
        </div>
      `;
    }
    return;
  }

  const client = new ArenaWebSocketClient({
    attemptId,
    onStateChange: (state) => {
      if (state.type === 'CONNECTION_STATE') {
        if (wsStatusEl) {
          wsStatusEl.textContent = `SOCKET: ${state.state}`;
          wsStatusEl.className =
            state.state === 'SAVED' || state.state === 'CONNECTED'
              ? 'tv-badge tv-badge--saved'
              : state.state === 'STALE_FENCED'
              ? 'tv-badge tv-badge--unavailable'
              : 'tv-badge tv-badge--pending';
        }
        if (ackWatermarkEl && state.watermark !== undefined) {
          ackWatermarkEl.textContent = `ACK: ${state.watermark}`;
        }
        if (pendingQueueEl && state.pendingCount !== undefined) {
          pendingQueueEl.textContent = state.pendingCount.toString();
        }
      } else if (state.type === 'ROUND_STATE') {
        const round = state.data;
        if (workspaceEl && round.challenge_content) {
          workspaceEl.innerHTML = `
            <div style="padding: 1rem;">
              <div class="tv-alert tv-alert--success" style="margin-bottom: 1rem;">
                <strong>Round Active!</strong> Typed keystrokes are streamed and acknowledged via <code>arena-ws-v1</code>.
              </div>
              <div class="tv-prompt-box" style="font-family: var(--tv-font-mono); font-size: var(--tv-text-lg); line-height: 1.8; padding: 1.5rem; background: var(--tv-bg-surface); border: 1px solid var(--tv-border-default); border-radius: var(--tv-radius-md);">
                ${round.challenge_content}
              </div>
            </div>
          `;
        }
      }
    },
    onAck: (ack) => {
      if (committedCharsEl) {
        committedCharsEl.textContent = ack.resulting_text_length.toString();
      }
    },
    onReject: (rej) => {
      console.warn('Batch rejected:', rej.rejection_reason);
    },
    onError: (err) => {
      console.error('Arena error:', err);
    },
  });

  client.connect();
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    initArenaPage();
  });
}

