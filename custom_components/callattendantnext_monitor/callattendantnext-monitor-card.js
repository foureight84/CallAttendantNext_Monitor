/**
 * CallAttendantNext Monitor Card
 * Lovelace custom card showing the most-recent call and paginated history.
 *
 * Usage in dashboard YAML:
 *   type: custom:callattendantnext-monitor-card
 *   title: "Phone Calls"              # optional, default "CallAttendantNext Monitor"
 *   page_size: 10                     # optional, default 10
 *   voicemail_base_url: "http://callattendantnext.local:3000/api/audio"  # optional
 */

class CallAttendantNextMonitorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._page = 0;
    this._pageSize = 10;
    this._title = "CallAttendantNext Monitor";
    this._voicemailBaseUrl = null;
    this._calls = [];
    this._total = 0;
    this._loading = true;
    this._error = null;
    this._hass = null;
    this._initialized = false;
    this._playingVoicemail = null; // filename currently expanded in the audio player
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;

    if (!this._initialized) {
      this._initialized = true;
      this._fetchHistory();
      return;
    }

    // Re-render hero + refresh history when a new call arrives.
    const SENSOR = "sensor.callattendantnext_monitor_last_call";
    const prevTs = prev && prev.states[SENSOR] && prev.states[SENSOR].attributes && prev.states[SENSOR].attributes.timestamp;
    const nextTs = hass && hass.states[SENSOR] && hass.states[SENSOR].attributes && hass.states[SENSOR].attributes.timestamp;
    if (prevTs !== nextTs) {
      this._page = 0;
      this._playingVoicemail = null;
      this._fetchHistory();
    }
  }

  setConfig(config) {
    this._config = config || {};
    this._pageSize = Math.min(100, Math.max(1, parseInt(this._config.page_size) || 10));
    this._title = this._config.title || "CallAttendantNext Monitor";
    this._voicemailBaseUrl = this._config.voicemail_base_url
      ? String(this._config.voicemail_base_url).replace(/\/$/, "")
      : null;
    this._render();
  }

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  async _fetchHistory() {
    if (!this._hass) return;
    this._loading = true;
    this._error = null;
    this._render();

    try {
      const result = await this._hass.callWS({
        type: "callattendantnext_monitor/history",
        page: this._page,
        page_size: this._pageSize,
      });
      this._calls = result.calls || [];
      this._total = result.total || 0;
    } catch (e) {
      this._error = e.message || "Failed to load call history.";
      console.error("[CallAttendantNext Monitor]", e);
    }

    this._loading = false;
    this._render();
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  _formatTimestamp(ts) {
    if (!ts) return "";
    try {
      return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(new Date(ts));
    } catch {
      return ts;
    }
  }

  _actionColor(action) {
    switch (action) {
      case "Permitted": return "var(--success-color, #4CAF50)";
      case "Screened":  return "var(--warning-color, #FF9800)";
      case "Blocked":   return "var(--error-color, #F44336)";
      default:          return "var(--disabled-color, #9E9E9E)";
    }
  }

  _actionIcon(action) {
    switch (action) {
      case "Permitted": return "✓";
      case "Screened":  return "●";
      case "Blocked":   return "✕";
      default:          return "?";
    }
  }

  _esc(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Voicemail button — toggles inline player when voicemail_base_url is set,
  // otherwise renders as a plain indicator.
  _voicemailBtn(filename, extraClass) {
    if (!filename) return "";
    if (!this._voicemailBaseUrl) {
      return `<span class="vm-btn ${extraClass}">🎙 Voicemail</span>`;
    }
    const active = this._playingVoicemail === filename ? " vm-active" : "";
    return `<button class="vm-btn ${extraClass}${active}" data-vm="${this._esc(filename)}">🎙 Voicemail</button>`;
  }

  // Inline audio player row for a given filename.
  _audioPlayerHtml(filename) {
    if (!filename || !this._voicemailBaseUrl || this._playingVoicemail !== filename) return "";
    const src = `${this._voicemailBaseUrl}/${this._esc(filename)}`;
    return `
      <li class="audio-row">
        <audio class="audio-player" controls autoplay src="${src}">
          Your browser does not support audio playback.
        </audio>
      </li>
    `;
  }

  // -----------------------------------------------------------------------
  // Hero (last-call) panel
  // -----------------------------------------------------------------------

  _renderHero() {
    if (!this._hass) return "";
    const state = this._hass.states["sensor.callattendantnext_monitor_last_call"];
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      return `<div class="hero hero-empty">No calls recorded yet.</div>`;
    }

    const action = state.state;
    const attrs = state.attributes || {};
    const color = this._actionColor(action);
    const vmFilename = attrs.voicemail || null;
    const audioPlayer = (vmFilename && this._voicemailBaseUrl && this._playingVoicemail === vmFilename)
      ? `<audio class="audio-player hero-audio" controls autoplay src="${this._voicemailBaseUrl}/${this._esc(vmFilename)}">Your browser does not support audio playback.</audio>`
      : "";

    return `
      <div class="hero" style="border-left: 4px solid ${color}">
        <div class="hero-top">
          <span class="hero-badge" style="background:${color}">${this._esc(action)}</span>
          ${this._voicemailBtn(vmFilename, "hero-voicemail")}
        </div>
        <div class="hero-name">${this._esc(attrs.name || "Unknown Caller")}</div>
        <div class="hero-meta">
          <span>${this._esc(attrs.number || "")}</span>
          ${attrs.reason ? `<span class="hero-dot">·</span><span>${this._esc(attrs.reason)}</span>` : ""}
        </div>
        <div class="hero-time">${this._esc(this._formatTimestamp(attrs.timestamp))}</div>
        ${audioPlayer}
      </div>
    `;
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  _render() {
    const totalPages = Math.max(1, Math.ceil(this._total / this._pageSize));
    const prevDisabled = this._page === 0 ? "disabled" : "";
    const nextDisabled = this._page >= totalPages - 1 ? "disabled" : "";

    let historyBody;
    if (this._loading) {
      historyBody = `<div class="state-msg">Loading…</div>`;
    } else if (this._error) {
      historyBody = `<div class="state-msg error">${this._esc(this._error)}</div>`;
    } else if (this._calls.length === 0) {
      historyBody = `<div class="state-msg">No call history yet.</div>`;
    } else {
      // On page 0 the first entry is the same call shown in the hero panel — skip it.
      const displayCalls = this._page === 0 ? this._calls.slice(1) : this._calls;
      if (displayCalls.length === 0) {
        historyBody = `<div class="state-msg">No older calls.</div>`;
      } else {
        const rows = displayCalls.map((call) => `
          <li class="call-row">
            <span class="badge" style="background:${this._actionColor(call.action)}" title="${this._esc(call.action)}">
              ${this._actionIcon(call.action)}
            </span>
            <div class="call-info">
              <div class="call-name">${this._esc(call.name || "Unknown")}</div>
              <div class="call-sub">${this._esc(call.number || "")}${call.reason ? ` · ${this._esc(call.reason)}` : ""}</div>
            </div>
            <div class="call-right">
              <div class="call-time">${this._esc(this._formatTimestamp(call.timestamp))}</div>
              ${this._voicemailBtn(call.voicemail, "voicemail-tag")}
            </div>
          </li>
          ${this._audioPlayerHtml(call.voicemail)}
        `).join("");

        historyBody = `
          <ul class="call-list">${rows}</ul>
          <div class="pagination">
            <button class="btn" id="prev-btn" ${prevDisabled}>&#8592; Prev</button>
            <span class="page-info">Page ${this._page + 1} of ${totalPages}<br><small>${this._total} total</small></span>
            <button class="btn" id="next-btn" ${nextDisabled}>Next &#8594;</button>
          </div>
        `;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }

        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.12));
          overflow: hidden;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          font-size: var(--paper-font-body1_-_font-size, 14px);
          color: var(--primary-text-color, #212121);
        }

        /* ── Card header ── */
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 14px 16px 10px;
          font-size: 1.05em;
          font-weight: 500;
          letter-spacing: .01em;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.12));
        }

        /* ── Hero panel ── */
        .hero {
          padding: 14px 16px;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.12));
          background: var(--secondary-background-color, rgba(0,0,0,.03));
        }
        .hero-empty {
          color: var(--secondary-text-color, #727272);
          font-size: 0.95em;
          border-left: none;
          text-align: center;
          padding: 16px;
        }
        .hero-top {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .hero-badge {
          display: inline-block;
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 0.82em;
          font-weight: 700;
          letter-spacing: .04em;
          text-transform: uppercase;
          color: #fff;
        }
        .hero-name {
          font-size: 1.05em;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .hero-meta {
          font-size: 0.92em;
          color: var(--secondary-text-color, #727272);
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .hero-dot { margin: 0 4px; }
        .hero-time {
          font-size: 0.88em;
          color: var(--secondary-text-color, #727272);
          margin-top: 4px;
        }
        .hero-audio {
          width: 100%;
          margin-top: 10px;
        }

        /* ── Section label ── */
        .section-label {
          padding: 8px 16px 4px;
          font-size: 0.78em;
          font-weight: 600;
          letter-spacing: .06em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #727272);
        }

        /* ── State messages ── */
        .state-msg {
          padding: 20px 16px;
          text-align: center;
          color: var(--secondary-text-color, #727272);
          font-size: 0.95em;
        }
        .state-msg.error { color: var(--error-color, #F44336); }

        /* ── Call list ── */
        .call-list { list-style: none; margin: 0; padding: 0; }
        .call-row {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 9px 16px;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.06));
        }

        .badge {
          flex-shrink: 0;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 700;
          color: #fff;
          margin-top: 2px;
        }

        .call-info { flex: 1; min-width: 0; }
        .call-name {
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .call-sub {
          font-size: 0.9em;
          color: var(--secondary-text-color, #727272);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          margin-top: 2px;
        }

        .call-right { flex-shrink: 0; text-align: right; }
        .call-time {
          font-size: 0.88em;
          color: var(--secondary-text-color, #727272);
          white-space: nowrap;
        }

        /* ── Voicemail button ── */
        .vm-btn {
          display: inline-block;
          font-size: 0.85em;
          color: var(--primary-color, #03a9f4);
          background: none;
          border: none;
          padding: 0;
          cursor: pointer;
          font-family: inherit;
          white-space: nowrap;
        }
        .vm-btn.voicemail-tag {
          display: block;
          text-align: right;
          margin-top: 3px;
        }
        .vm-btn.hero-voicemail {
          font-size: 0.88em;
        }
        .vm-btn.vm-active {
          font-weight: 600;
          text-decoration: underline;
        }
        button.vm-btn:hover { opacity: 0.75; }

        /* ── Inline audio player ── */
        .audio-row {
          list-style: none;
          padding: 6px 16px 10px 56px;
          border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.06));
        }
        .audio-player {
          width: 100%;
          height: 36px;
        }

        /* ── Pagination ── */
        .pagination {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 16px;
          border-top: 1px solid var(--divider-color, rgba(0,0,0,.12));
        }
        .btn {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border: none;
          border-radius: 4px;
          padding: 6px 14px;
          font-size: 0.9em;
          cursor: pointer;
          transition: opacity 0.15s;
        }
        .btn:hover:not(:disabled) { opacity: 0.85; }
        .btn:disabled { background: var(--disabled-color, #bdbdbd); cursor: default; }
        .page-info {
          font-size: 0.9em;
          color: var(--secondary-text-color, #727272);
          text-align: center;
          line-height: 1.4;
        }
        .page-info small { font-size: 0.9em; }
      </style>

      <div class="card">
        <div class="card-header">
          <span>☎️</span>
          <span>${this._esc(this._title)}</span>
        </div>
        ${this._renderHero()}
        <div class="section-label">History</div>
        ${historyBody}
      </div>
    `;

    // Wire up pagination buttons.
    const prevBtn = this.shadowRoot.getElementById("prev-btn");
    const nextBtn = this.shadowRoot.getElementById("next-btn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (this._page > 0) { this._page--; this._playingVoicemail = null; this._fetchHistory(); }
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (this._page < Math.ceil(this._total / this._pageSize) - 1) {
          this._page++; this._playingVoicemail = null; this._fetchHistory();
        }
      });
    }

    // Wire up voicemail toggle buttons.
    this.shadowRoot.querySelectorAll("button.vm-btn[data-vm]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const filename = btn.dataset.vm;
        this._playingVoicemail = this._playingVoicemail === filename ? null : filename;
        this._render();
      });
    });
  }

  // -----------------------------------------------------------------------
  // Card metadata
  // -----------------------------------------------------------------------

  static getStubConfig() {
    return { type: "custom:callattendantnext-monitor-card", page_size: 10 };
  }

  getCardSize() {
    return Math.ceil(this._pageSize / 2) + 3;
  }
}

customElements.define("callattendantnext-monitor-card", CallAttendantNextMonitorCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "callattendantnext-monitor-card",
  name: "CallAttendantNext Monitor",
  description: "Live last-call panel and paginated call history from CallAttendantNext.",
  preview: false,
});
