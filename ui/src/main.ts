import { LitElement, html } from "lit";
import { DashboardStore, sectionFromHash, sections, type Section } from "./model.ts";
import { styles } from "./styles.ts";
import { dateText, renderLoadState, renderSection, snapshotStatus } from "./views.ts";

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

  render() {
    const snapshot = this.store.snapshot;
    const state = this.store.state;
    const status = snapshotStatus(state);
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
          ${status ? html`<span class="status" data-tone=${status.tone}>${status.label}</span>` : html``}</div>
        <div role="status" aria-live="polite">
          ${renderLoadState(state)}
        </div>
        ${snapshot ? renderSection(this.section, snapshot) : html``}
        ${snapshot ? html`<p class="muted">Last successful read: ${dateText(snapshot.generated_at)}</p>` : html``}
      </main>
      <footer>Symphonia · App status and stored data</footer>
    </div>`;
  }
}

customElements.define("sym-dashboard", SymDashboard);
