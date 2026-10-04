export type Section = "overview" | "connections" | "library" | "activity" | "diagnostics";
export const sections: readonly Section[] = ["overview", "connections", "library", "activity", "diagnostics"];

export type Dashboard = {
  service: "symphonia";
  version: string;
  ready: true;
  generated_at: string;
  queue: { total: number; eligible_count: number; states: Record<string, number> };
  connections: { total: number; expired_count: number; by_provider: Record<string, Record<string, number>> };
  library: { current_playlists: number; entries: number; unavailable_entries: number; latest_published_at: string | null };
  resolutions: { total: number; by_action: Record<string, number> };
  operations: { id: string; type: string; state: string; updated_at: string | null }[];
};

export type ViewState = "loading" | "ready" | "empty" | "refreshing" | "stale" | "blocked";

export function sectionFromHash(hash: string): Section {
  const value = hash.replace(/^#\//, "");
  return sections.includes(value as Section) ? value as Section : "overview";
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function count(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function counts(value: unknown): value is Record<string, number> {
  return record(value) && Object.values(value).every(count);
}

function queue(value: unknown): value is Dashboard["queue"] {
  return record(value) && count(value.total) && count(value.eligible_count) && counts(value.states);
}

function connections(value: unknown): value is Dashboard["connections"] {
  return record(value) && count(value.total) && count(value.expired_count) &&
    record(value.by_provider) && Object.values(value.by_provider).every(counts);
}

function library(value: unknown): value is Dashboard["library"] {
  return record(value) && count(value.current_playlists) && count(value.entries) &&
    count(value.unavailable_entries) &&
    (value.latest_published_at === null || typeof value.latest_published_at === "string");
}

function resolutions(value: unknown): value is Dashboard["resolutions"] {
  return record(value) && count(value.total) && counts(value.by_action);
}

function operation(value: unknown): value is Dashboard["operations"][number] {
  return record(value) && typeof value.id === "string" && typeof value.type === "string" &&
    typeof value.state === "string" &&
    (value.updated_at === null || typeof value.updated_at === "string");
}

function operations(value: unknown): value is Dashboard["operations"] {
  return Array.isArray(value) && value.length <= 10 && value.every(operation);
}

export function isDashboard(value: unknown): value is Dashboard {
  if (!record(value)) return false;
  return value.service === "symphonia" && value.ready === true &&
    typeof value.generated_at === "string" && typeof value.version === "string" &&
    queue(value.queue) && connections(value.connections) && library(value.library) &&
    resolutions(value.resolutions) && operations(value.operations);
}

export function hasStoredData(snapshot: Dashboard): boolean {
  return snapshot.queue.total > 0 || snapshot.connections.total > 0 ||
    snapshot.library.current_playlists > 0 || snapshot.resolutions.total > 0;
}

export class DashboardStore {
  state: ViewState = "loading";
  snapshot: Dashboard | null = null;
  private generation = 0;
  private readonly changed: () => void;

  constructor(changed: () => void) { this.changed = changed; }

  async refresh(read: () => Promise<unknown>): Promise<void> {
    const current = ++this.generation;
    this.state = this.snapshot ? "refreshing" : "loading";
    this.changed();
    try {
      const value = await read();
      if (current !== this.generation) return;
      if (!isDashboard(value)) throw new Error("invalid_dashboard");
      this.snapshot = value;
      this.state = hasStoredData(value) ? "ready" : "empty";
    } catch {
      if (current !== this.generation) return;
      this.state = this.snapshot ? "stale" : "blocked";
    }
    this.changed();
  }
}
