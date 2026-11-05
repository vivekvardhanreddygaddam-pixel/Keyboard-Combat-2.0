/**
 * TypeVector Arena — Ranked WebSocket Client (arena-ws-v1)
 *
 * Implements server-authoritative monotonic sequence admission,
 * writer-generation fencing, pending batch queues, and transparent durability status.
 */

const PROTOCOL_VERSION = 'arena-ws-v1';

export class ArenaWebSocketClient {
  constructor(options = {}) {
    this.attemptId = options.attemptId || null;
    this.token = options.token || null;
    this.onStateChange = options.onStateChange || (() => {});
    this.onAck = options.onAck || (() => {});
    this.onReject = options.onReject || (() => {});
    this.onError = options.onError || (() => {});

    this.socket = null;
    this.writerGeneration = 1;
    this.nextSequence = 1;
    this.lastAckedSequence = 0;
    this.pendingBatches = new Map(); // seq -> batch
    this.localProjection = '';
    this.roundState = null;
    this.deadlineAt = null;

    this.isConnected = false;
    this.isReconnecting = false;
    this.clientSessionId = 'sess_' + Math.random().toString(36).substring(2, 12);
  }

  /**
   * Connect to the server WebSocket endpoint.
   */
  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    let url = `${protocol}//${host}/api/v1/arena/ws`;
    if (this.token) {
      url += `?token=${encodeURIComponent(this.token)}`;
    }

    this.socket = new WebSocket(url);

    this.socket.addEventListener('open', () => {
      this.isConnected = true;
      this.isReconnecting = false;
      this.updateStatus('CONNECTING', 'Initiating attempt binding...');

      // Send CONNECT_ATTEMPT
      if (this.attemptId) {
        this.send({
          protocol_version: PROTOCOL_VERSION,
          type: 'CONNECT_ATTEMPT',
          attempt_id: this.attemptId,
          client_session_id: this.clientSessionId,
          auth_token: this.token,
          sent_at: new Date().toISOString(),
        });
      }
    });

    this.socket.addEventListener('message', (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleMessage(msg);
      } catch (err) {
        console.error('Failed to parse incoming WebSocket message:', err);
      }
    });

    this.socket.addEventListener('close', (event) => {
      this.isConnected = false;
      if (event.code === 4409) {
        this.updateStatus('STALE_FENCED', 'Tab evicted: newer writer connection active.');
        this.onError({ code: 'STALE_WRITER_EVICTED', message: 'Evicted by newer generation' });
        return;
      }

      this.updateStatus('OFFLINE', `Disconnected (code: ${event.code}). Reconnecting...`);
      this.scheduleReconnect();
    });

    this.socket.addEventListener('error', (err) => {
      console.warn('Arena WebSocket error:', err);
    });
  }

  scheduleReconnect() {
    if (this.isReconnecting) return;
    this.isReconnecting = true;
    setTimeout(() => {
      if (!this.isConnected) {
        this.connect();
      }
    }, 2000);
  }

  handleMessage(msg) {
    switch (msg.type) {
      case 'CONNECTED':
        this.writerGeneration = msg.writer_generation;
        this.lastAckedSequence = msg.last_committed_sequence;
        this.nextSequence = this.lastAckedSequence + 1;
        this.deadlineAt = msg.deadline_at ? new Date(msg.deadline_at) : null;
        this.updateStatus('CONNECTED', `Active (Gen ${this.writerGeneration})`);
        this.replayPendingBatches();
        break;

      case 'ROUND_STATE':
        this.roundState = msg;
        this.onStateChange({ type: 'ROUND_STATE', data: msg });
        break;

      case 'INPUT_ACK':
        this.handleAck(msg);
        break;

      case 'INPUT_REJECTED':
        this.handleReject(msg);
        break;

      case 'RESUME_STATE':
        this.writerGeneration = msg.writer_generation;
        this.lastAckedSequence = msg.last_committed_sequence;
        this.nextSequence = this.lastAckedSequence + 1;
        this.localProjection = msg.materialized_text_projection;
        this.replayPendingBatches();
        break;

      case 'CLOCK_SAMPLE':
        break;

      case 'ERROR':
        this.onError(msg);
        break;
    }
  }

  handleAck(ack) {
    // Drop all confirmed batches up through committed_sequence_watermark
    for (const seq of this.pendingBatches.keys()) {
      if (seq <= ack.committed_sequence_watermark) {
        this.pendingBatches.delete(seq);
      }
    }
    this.lastAckedSequence = ack.committed_sequence_watermark;
    this.updateStatus('SAVED', `Saved through Seq #${this.lastAckedSequence}`);
    this.onAck(ack);
  }

  handleReject(rej) {
    console.warn('Batch rejected by server:', rej);
    this.onReject(rej);

    if (rej.rejection_reason === 'OUT_OF_ORDER_SEQUENCE') {
      this.requestResume();
    } else if (rej.rejection_reason === 'STALE_GENERATION') {
      this.updateStatus('STALE_FENCED', 'Rejected: writer generation is stale.');
    }
  }

  requestResume() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.send({
        protocol_version: PROTOCOL_VERSION,
        type: 'RESUME_REQUEST',
        attempt_id: this.attemptId,
        last_received_ack_sequence: this.lastAckedSequence,
        client_session_id: this.clientSessionId,
      });
    }
  }

  /**
   * Submit an input batch with client operations.
   */
  async submitBatch(operations) {
    if (!operations || operations.length === 0) return;

    const seq = this.nextSequence++;
    const digest = await this.computeDigest(operations);

    const batch = {
      protocol_version: PROTOCOL_VERSION,
      type: 'INPUT_BATCH',
      attempt_id: this.attemptId,
      batch_sequence_number: seq,
      writer_generation: this.writerGeneration,
      operations: operations,
      payload_digest_sha256: digest,
      client_sent_at: new Date().toISOString(),
    };

    this.pendingBatches.set(seq, batch);
    this.updateStatus('PENDING', `Pending Seq #${seq} (In-flight: ${this.pendingBatches.size})`);

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(batch));
    }
  }

  replayPendingBatches() {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;

    // Filter and replay batches with seq > lastAckedSequence
    const sortedSeqs = Array.from(this.pendingBatches.keys()).sort((a, b) => a - b);
    for (const seq of sortedSeqs) {
      if (seq <= this.lastAckedSequence) {
        this.pendingBatches.delete(seq);
        continue;
      }
      const batch = this.pendingBatches.get(seq);
      // Update generation to current active generation
      batch.writer_generation = this.writerGeneration;
      this.socket.send(JSON.stringify(batch));
    }
  }

  send(data) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    }
  }

  async computeDigest(operations) {
    const normalized = operations.map((op) => {
      if (op.type === 'backspace') {
        return { count: op.count, type: 'backspace' };
      }
      return { text: op.text, type: 'insert' };
    });
    const canonicalStr = JSON.stringify(normalized);
    const encoder = new TextEncoder();
    const data = encoder.encode(canonicalStr);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  updateStatus(state, details) {
    this.onStateChange({
      type: 'CONNECTION_STATE',
      state,
      details,
      watermark: this.lastAckedSequence,
      pendingCount: this.pendingBatches.size,
      generation: this.writerGeneration,
    });
  }
}

