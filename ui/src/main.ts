import { LitElement, html } from "lit";
import { DashboardStore, sectionFromHash, sections, type Dashboard, type Section } from "./model.ts";
import { styles } from "./styles.ts";

function dateText(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Not available" : date.toLocaleString();
}

function stateTone(value: string): string {
  if (["completed", "succeeded", "ready", "active"].includes(value)) return "positive";
  if (["failed", "cancelled", "blocked"].includes(value)) return "negative";
  return "caution";
}

class SymDashboard extends LitElement {
  static styles = styles;
  private readonly store = new DashboardStore(() => this.requestUpdate());
  private readonly colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
  private dark = this.colorScheme.matches;
  private section: Section = sectionFromHash(window.location.hash);
  private readonly onScheme = (event: MediaQueryListEvent): void => { this.dark = event.matches; this.requestUpdate(); };
  private readonly onHash = (): void => {
    this.section = sectionFromHash(window.location.hash);
    this.requestUpdate();
    void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLElement>("h1")?.focus());
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.colorScheme.addEventListener("change", this.onScheme);
    window.addEventListener("hashchange", this.onHash);
    void this.refresh();
  }

  disconnectedCallback(): void {
    this.colorScheme.removeEventListener("change", this.onScheme);
    window.removeEventListener("hashchange", this.onHash);
    super.disconnectedCallback();
  }

  private async refresh(): Promise<void> {
    await this.store.refresh(async () => {
      const response = await fetch("./api/dashboard", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("dashboard_unavailable");
      return response.json() as Promise<unknown>;
    });
  }

  private skip(): void { this.renderRoot.querySelector<HTMLElement>("main")?.focus(); }
  private toggleTheme(): void { this.dark = !this.dark; this.requestUpdate(); }

  private renderOverview(snapshot: Dashboard) {
    return html`
      <div class="grid">
        <section class="panel"><h2>Operations</h2><p class="metric">${snapshot.queue.total}</p><p class="muted">${snapshot.queue.eligible_count} eligible to run</p></section>
        <section class="panel"><h2>Connections</h2><p class="metric">${snapshot.connections.total}</p><p class="muted">${snapshot.connections.expired_count} expired</p></section>
        <section class="panel"><h2>Library</h2><p class="metric">${snapshot.library.current_playlists}</p><p class="muted">current playlists · ${snapshot.library.entries} entries</p></section>
      </div>
      <section class="panel"><h2>Next steps</h2><p>Provider setup, library import, playback, and playlist copy are not available in this build. This dashboard reflects stored App data only.</p></section>
    `;
  }

  private renderConnections(snapshot: Dashboard) {
    const providers = Object.entries(snapshot.connections.by_provider);
    return html`<section class="panel"><h2>Stored connections</h2>
      ${providers.length ? providers.map(([provider, states]) => html`<div class="row"><div class="row-copy"><strong>${provider}</strong><small>${Object.entries(states).map(([state, count]) => `${state}: ${count}`).join(" · ")}</small></div></div>`) : html`<p>No connections recorded. Provider setup is not available in this build.</p>`}
      <p class="muted">${snapshot.connections.expired_count} connection records have expired credentials.</p>
    </section>`;
  }

  private renderLibrary(snapshot: Dashboard) {
    return html`<section class="panel"><h2>Stored library projection</h2><dl>
      <div class="fact"><dt>Current playlists</dt><dd>${snapshot.library.current_playlists}</dd></div>
      <div class="fact"><dt>Entries</dt><dd>${snapshot.library.entries}</dd></div>
      <div class="fact"><dt>Unavailable entries</dt><dd>${snapshot.library.unavailable_entries}</dd></div>
      <div class="fact"><dt>Last published</dt><dd>${dateText(snapshot.library.latest_published_at)}</dd></div>
    </dl><p class="muted">Import controls are not available in this build.</p></section>`;
  }

  private renderActivity(snapshot: Dashboard) {
    return html`<section class="panel"><h2>Recent operations</h2>
      ${snapshot.operations.length ? snapshot.operations.map(operation => html`<div class="row">
        <div class="row-copy"><strong>${operation.type || "Operation"}</strong><small>${operation.id} · Updated ${dateText(operation.updated_at)}</small></div>
        <span class="status" data-tone=${stateTone(operation.state)}>${operation.state || "unknown"}</span>
      </div>`) : html`<p>No operations recorded.</p>`}
    </section>`;
  }

  private renderDiagnostics(snapshot: Dashboard) {
    return html`<section class="panel"><h2>App diagnostics</h2><dl>
      <div class="fact"><dt>Service</dt><dd>Ready</dd></div>
      <div class="fact"><dt>Version</dt><dd>${snapshot.version}</dd></div>
      <div class="fact"><dt>Queue states</dt><dd>${Object.entries(snapshot.queue.states).map(([state, count]) => `${state}: ${count}`).join(" · ") || "None"}</dd></div>
      <div class="fact"><dt>Identity decisions</dt><dd>${snapshot.resolutions.total}</dd></div>
      <div class="fact"><dt>Last successful read</dt><dd>${dateText(snapshot.generated_at)}</dd></div>
    </dl><p class="muted">Detailed payloads, account identifiers, and credentials are never shown here.</p></section>`;
  }

  private renderSection(snapshot: Dashboard) {
    switch (this.section) {
      case "connections": return this.renderConnections(snapshot);
      case "library": return this.renderLibrary(snapshot);
      case "activity": return this.renderActivity(snapshot);
      case "diagnostics": return this.renderDiagnostics(snapshot);
      default: return this.renderOverview(snapshot);
    }
  }

  render() {
    const snapshot = this.store.snapshot;
    const state = this.store.state;
    return html`<div class=${this.dark ? "dark" : "light"}>
      <button class="skip" type="button" @click=${this.skip}>Skip to content</button>
      <header class="topbar"><div class="topbar-inner">
        <div class="brand"><span class="brand-mark" aria-hidden="true">♫</span><strong>Symphonia</strong></div>
        <div class="top-actions"><button type="button" @click=${() => void this.refresh()} ?disabled=${state === "refreshing" || state === "loading"}>Refresh</button>
          <button class="theme" type="button" @click=${this.toggleTheme} aria-label=${`Switch to ${this.dark ? "light" : "dark"} theme`}>${this.dark ? "☀" : "☾"}</button></div>
      </div></header>
      <nav class="tabs" aria-label="Symphonia sections"><div class="tabs-inner">
        ${sections.map(section => html`<a href=${`#/${section}`} aria-current=${this.section === section ? "page" : "false"}>${section.charAt(0).toUpperCase() + section.slice(1)}</a>`)}
      </div></nav>
      <main id="content" tabindex="-1">
        <div class="heading"><div><p class="eyebrow">Home Assistant App</p><h1 tabindex="-1">${this.section.charAt(0).toUpperCase() + this.section.slice(1)}</h1><p class="muted">Live operational state from Symphonia</p></div>
          ${snapshot ? html`<span class="status" data-tone="positive">Storage ready</span>` : html``}</div>
        <div role="status" aria-live="polite">
          ${state === "loading" ? html`<div class="alert">Loading stored status…</div>` : html``}
          ${state === "refreshing" ? html`<div class="alert">Refreshing stored status…</div>` : html``}
          ${state === "blocked" ? html`<div class="alert" data-tone="negative"><strong>Status unavailable.</strong><p>Check that the App is running, then retry.</p></div>` : html``}
          ${state === "stale" ? html`<div class="alert" data-tone="caution"><strong>Could not refresh.</strong><p>Showing the last successful snapshot. Try again or check App logs.</p></div>` : html``}
          ${state === "empty" ? html`<div class="alert" data-tone="caution"><strong>No stored data yet.</strong><p>The App is ready, but no connections, playlists, or operations are recorded.</p></div>` : html``}
        </div>
        ${snapshot ? this.renderSection(snapshot) : html``}
        ${snapshot ? html`<p class="muted">Last successful read: ${dateText(snapshot.generated_at)}</p>` : html``}
      </main>
      <footer>Symphonia · App status and stored data</footer>
    </div>`;
  }
}

customElements.define("sym-dashboard", SymDashboard);
