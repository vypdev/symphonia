/** Session-local preference: system updates never replace an explicit choice. */
export class ThemeState {
  private preference: "auto" | "light" | "dark" = "auto";
  private systemDark: boolean;
  constructor(systemDark: boolean) { this.systemDark = systemDark; }

  get dark(): boolean {
    return this.preference === "auto" ? this.systemDark : this.preference === "dark";
  }

  systemChanged(dark: boolean): void { this.systemDark = dark; }
  toggle(): void { this.preference = this.dark ? "light" : "dark"; }
}
