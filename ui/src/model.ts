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

export function isDashboard(value: unknown): value is Dashboard {
  if (!record(value)) return false;
  const item = value;
  const queue = item.queue;
  const connections = item.connections;
  const library = item.library;
  const resolutions = item.resolutions;
  return item.service === "symphonia" && item.ready === true &&
    typeof item.generated_at === "string" && typeof item.version === "string" &&
    record(queue) && count(queue.total) && count(queue.eligible_count) && counts(queue.states) &&
    record(connections) && count(connections.total) && count(connections.expired_count) &&
    record(connections.by_provider) && Object.values(connections.by_provider).every(counts) &&
    record(library) && count(library.current_playlists) && count(library.entries) &&
    count(library.unavailable_entries) && (library.latest_published_at === null || typeof library.latest_published_at === "string") &&
    record(resolutions) && count(resolutions.total) && counts(resolutions.by_action) &&
    Array.isArray(item.operations) && item.operations.length <= 10 && item.operations.every(operation =>
      record(operation) && typeof operation.id === "string" && typeof operation.type === "string" &&
      typeof operation.state === "string" && (operation.updated_at === null || typeof operation.updated_at === "string"));
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
