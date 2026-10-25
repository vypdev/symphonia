export const sections = ["overview", "listening", "connections", "library", "matches", "copy", "activity"] as const;
export type Section = (typeof sections)[number];

export const scenarios = ["ready", "partial", "attention", "offline"] as const;
export type Scenario = (typeof scenarios)[number];

export function sectionFromHash(hash: string): Section {
  const candidate = hash.replace(/^#\/?/, "").split(/[/?]/, 1)[0];
  return sections.find((section) => section === candidate) ?? "overview";
}

export function scenarioLabel(scenario: Scenario): string {
  return {
    ready: "Up to date",
    partial: "Partial result",
    attention: "Action required",
    offline: "Unavailable",
  }[scenario];
}

export function scenarioTone(scenario: Scenario): "positive" | "caution" | "negative" {
  return scenario === "ready" ? "positive" : scenario === "offline" ? "negative" : "caution";
}
