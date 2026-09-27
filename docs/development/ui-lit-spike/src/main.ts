import { LitElement, css, html } from "lit";
import { resolveTheme, type Preference } from "./appearance.ts";

type Section = "connections" | "library" | "activity";
const sections: readonly Section[] = ["connections", "library", "activity"];

class SymUiSpike extends LitElement {
  static properties = {
    preference: { state: true },
    section: { state: true },
    systemDark: { state: true },
  };

  private preference: Preference = "auto";
  private section: Section = "connections";
  private readonly colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
  private systemDark = this.colorScheme.matches;
  private readonly onColorSchemeChange = (event: MediaQueryListEvent): void => {
    this.systemDark = event.matches;
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.colorScheme.addEventListener("change", this.onColorSchemeChange);
  }

  disconnectedCallback(): void {
    this.colorScheme.removeEventListener("change", this.onColorSchemeChange);
    super.disconnectedCallback();
  }

  private selectSection(section: Section): void {
    this.section = section;
  }

  private toggleTheme(): void {
    this.preference = this.theme === "dark" ? "light" : "dark";
  }

  private get theme(): "light" | "dark" {
    return resolveTheme(this.preference, this.systemDark);
  }

  render() {
    const theme = this.theme;
    return html`
      <div class=${theme}>
        <header><strong>Symphonia</strong><span>UI tooling spike · synthetic data</span><button type="button" @click=${this.toggleTheme} aria-label=${`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>◐</button></header>
        <nav aria-label="Sections">${sections.map((section) => html`<button type="button" aria-current=${this.section === section ? "page" : "false"} @click=${() => this.selectSection(section)}>${section}</button>`)}</nav>
        <main>
          <h1>${this.section === "connections" ? "Connections" : this.section === "library" ? "Library" : "Activity"}</h1>
          <p>Presentation-only fixture. No provider or Home Assistant connection.</p>
          ${this.section === "connections" ? html`<article><h2>Source service</h2><p>Connected · last complete import at 09:14</p></article>` : this.section === "library" ? html`<article><h2>Library available with limitations</h2><p>12 playlists retained. Retry the incomplete import; no existing entries were removed.</p></article>` : html`<article><h2>Copy needs reconciliation</h2><p>Destination outcome is unknown. Inspect the durable operation before retrying; no success is inferred.</p></article>`}
        </main>
      </div>
    `;
  }

  static styles = css`
    :host { display: block; font: 14px/1.45 system-ui, sans-serif; }
    *, *::before, *::after { box-sizing: border-box; }
    .light { --canvas: #fafafa; --surface: #fff; --border: #e5e5e5; --text: #1a1a1a; --secondary: #616161; --accent: #008db8; }
    .dark { --canvas: #141414; --surface: #242424; --border: #555; --text: #f7f7f7; --secondary: #d0d0d0; --accent: #49c7ef; }
    .light, .dark { min-height: 100vh; color: var(--text); background: var(--canvas); }
    header, nav { display: flex; align-items: center; gap: 16px; padding: 12px max(16px, calc((100% - 960px) / 2)); border-bottom: 1px solid var(--border); background: var(--surface); }
    header span { margin-inline-start: auto; color: var(--secondary); font-size: 12px; }
    button { min-height: 40px; border: 0; color: inherit; background: transparent; cursor: pointer; }
    button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
    nav { gap: 0; overflow-x: auto; }
    nav button { padding: 0 14px; border-bottom: 2px solid transparent; text-transform: capitalize; }
    nav button[aria-current="page"] { border-bottom-color: var(--accent); font-weight: 700; }
    main { max-width: 992px; margin: auto; padding: 24px 16px; }
    h1 { margin: 0; font-size: 28px; font-weight: 500; }
    main > p, article p { color: var(--secondary); }
    article { max-width: 640px; margin-top: 24px; padding: 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
    h2 { margin: 0; font-size: 18px; font-weight: 500; }
    @media (max-width: 600px) { header span { display: none; } header button { margin-inline-start: auto; } }
    @media (forced-colors: active) { article, nav button[aria-current="page"] { border-color: CanvasText; } }
  `;
}

customElements.define("sym-ui-spike", SymUiSpike);
