export type Theme = "light" | "dark";
export type Preference = Theme | "auto";

// Browser fallback only. No Home Assistant theme property has been verified.
export function resolveTheme(preference: Preference, prefersDark: boolean): Theme {
  if (preference === "light" || preference === "dark") return preference;
  return prefersDark ? "dark" : "light";
}
