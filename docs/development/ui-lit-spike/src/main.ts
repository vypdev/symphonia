import { LitElement, html } from "lit";
import { resolveTheme, type Preference } from "./appearance.ts";
import { scenarioLabel, scenarios, sectionFromHash, sections, type Scenario, type Section } from "./fixture-state.ts";
import { viewFor } from "./fixture-views.ts";
import { styles } from "./styles.ts";

class SymUiSpike extends LitElement {
  static properties = {
    preference: { state: true },
    section: { state: true },
    scenario: { state: true },
    systemDark: { state: true },
  };

  declare private preference: Preference;
  declare private section: Section;
  declare private scenario: Scenario;
  private readonly colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
  declare private systemDark: boolean;
  private readonly onColorSchemeChange = (event: MediaQueryListEvent): void => {
    this.systemDark = event.matches;
  };
  private readonly onHashChange = (): void => {
    this.section = sectionFromHash(window.location.hash);
    void this.updateComplete.then(() => this.renderRoot.querySelector<HTMLElement>("h1")?.focus());
  };

  constructor() {
    super();
    this.preference = "auto";
    this.section = sectionFromHash(window.location.hash);
    this.scenario = "ready";
    this.systemDark = this.colorScheme.matches;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.colorScheme.addEventListener("change", this.onColorSchemeChange);
    window.addEventListener("hashchange", this.onHashChange);
  }

  disconnectedCallback(): void {
    this.colorScheme.removeEventListener("change", this.onColorSchemeChange);
    window.removeEventListener("hashchange", this.onHashChange);
    super.disconnectedCallback();
  }

  private toggleTheme(): void {
    this.preference = this.theme === "dark" ? "light" : "dark";
  }

  private skipToContent(): void {
    this.renderRoot.querySelector<HTMLElement>("main")?.focus();
  }

  private onScenarioChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    if (scenarios.some((scenario) => scenario === value)) this.scenario = value as Scenario;
  }

  private get theme(): "light" | "dark" {
    return resolveTheme(this.preference, this.systemDark);
  }

  render() {
    return html`<div class=${this.theme}>
      <button type="button" class="skip-link" @click=${this.skipToContent}>Skip to content</button>
      <header class="topbar"><div class="topbar-inner">
        <div class="brand"><span class="brand-mark" aria-hidden="true">♫</span><strong>Symphonia</strong><span class="fixture-label">UI review fixture</span></div>
        <button type="button" class="theme-button" @click=${this.toggleTheme} aria-label=${`Switch to ${this.theme === "dark" ? "light" : "dark"} theme`}>${this.theme === "dark" ? "☀" : "☾"}</button>
      </div></header>
      <nav class="tabs" aria-label="Music sections"><div class="tabs-inner">
        ${sections.map((section) => html`<a href=${`#/${section}`} aria-current=${this.section === section ? "page" : "false"}>${section === "copy" ? "Copy" : section.charAt(0).toUpperCase() + section.slice(1)}</a>`)}
      </div></nav>
      <main id="content" tabindex="-1">
        <div class="review-banner"><span><strong>Synthetic review data.</strong> No Home Assistant, provider, or App connection.</span>
          <label>Source data state <select aria-label="Source data state" .value=${this.scenario} @change=${this.onScenarioChange}>
            ${scenarios.map((scenario) => html`<option value=${scenario}>${scenarioLabel(scenario)}</option>`)}
          </select></label>
        </div>
        ${viewFor(this.section, this.scenario)}
      </main>
      <footer>Symphonia interface study · actions remain unavailable until their contracts and integrations are validated.</footer>
    </div>`;
  }

  static styles = styles;
}

customElements.define("sym-ui-spike", SymUiSpike);
