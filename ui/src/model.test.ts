import assert from "node:assert/strict";
import { test } from "node:test";
import { DashboardStore, hasStoredData, isDashboard, sectionFromHash, type Dashboard } from "./model.ts";
import { snapshotStatus } from "./views.ts";

const empty: Dashboard = {
  service: "symphonia", version: "0.1.0", ready: true,
  generated_at: "2026-10-04T12:00:00+00:00",
  queue: { total: 0, eligible_count: 0, states: {} },
  connections: { total: 0, expired_count: 0, by_provider: {} },
  library: { current_playlists: 0, entries: 0, unavailable_entries: 0, latest_published_at: null },
  resolutions: { total: 0, by_action: {} }, operations: [],
};

test("hash navigation stays within known dashboard sections", () => {
  assert.equal(sectionFromHash("#/activity"), "activity");
  assert.equal(sectionFromHash("#/../../outside"), "overview");
  assert.equal(sectionFromHash(""), "overview");
});

test("a valid empty response is distinguished from a failed read", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => empty);
  assert.equal(store.state, "empty");
  assert.equal(store.snapshot, empty);
  assert.equal(hasStoredData({ ...empty, queue: { ...empty.queue, total: 1 } }), true);
});

test("recent operations keep the dashboard ready even with zero aggregate counts", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => ({ ...empty, operations: [{ id: "op-1", type: "copy", state: "failed", updated_at: null }] }));
  assert.equal(store.state, "ready");
});

test("retained library entries keep the dashboard ready without a current playlist", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => ({ ...empty, library: { ...empty.library, entries: 1 } }));
  assert.equal(store.state, "ready");
});

test("unavailable library entries are stored data rather than an empty dashboard", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => ({ ...empty, library: { ...empty.library, unavailable_entries: 1 } }));
  assert.equal(store.state, "ready");
});

test("initial failure is blocked and a later failure retains a stale snapshot", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => { throw new Error("secret failure"); });
  assert.equal(store.state, "blocked");
  await store.refresh(async () => empty);
  await store.refresh(async () => { throw new Error("secret failure"); });
  assert.equal(store.state, "stale");
  assert.equal(store.snapshot, empty);
});

test("an older response cannot overwrite a newer refresh", async () => {
  const store = new DashboardStore(() => {});
  let release!: (value: Dashboard) => void;
  const first = store.refresh(() => new Promise<Dashboard>(resolve => { release = resolve; }));
  const newer = { ...empty, version: "new", queue: { ...empty.queue, total: 1 } };
  await store.refresh(async () => newer);
  release(empty);
  await first;
  assert.equal(store.snapshot?.version, "new");
  assert.equal(store.state, "ready");
});

test("malformed or nonready API data never becomes a ready screen", async () => {
  assert.equal(isDashboard({ service: "symphonia", ready: false }), false);
  const store = new DashboardStore(() => {});
  await store.refresh(async () => ({ ...empty, operations: "not-an-array" }));
  assert.equal(store.state, "blocked");
  await store.refresh(async () => ({ ...empty, queue: { ...empty.queue, states: { queued: "1" } } }));
  assert.equal(store.state, "blocked");
});

test("nested malformed data and oversized operation lists are rejected", () => {
  assert.equal(isDashboard({ ...empty, connections: { ...empty.connections, by_provider: { spotify: { active: -1 } } } }), false);
  assert.equal(isDashboard({ ...empty, library: { ...empty.library, unavailable_entries: 1.5 } }), false);
  assert.equal(isDashboard({ ...empty, operations: Array(11).fill({ id: "x", type: "copy", state: "queued", updated_at: null }) }), false);
  assert.equal(isDashboard({ ...empty, operations: [{ id: "x", type: "copy", state: "queued", updated_at: 42 }] }), false);
});

test("status pill reflects freshness and never marks a stale snapshot healthy", () => {
  assert.deepEqual(snapshotStatus("ready"), { label: "Storage ready", tone: "positive" });
  assert.deepEqual(snapshotStatus("refreshing"), { label: "Refreshing", tone: "caution" });
  assert.deepEqual(snapshotStatus("stale"), { label: "Snapshot stale", tone: "caution" });
  assert.equal(snapshotStatus("blocked"), null);
});

test("disconnect aborts the active read and fences its late successful response", async () => {
  let updates = 0;
  const store = new DashboardStore(() => { updates++; });
  let signal!: AbortSignal;
  let release!: (value: Dashboard) => void;
  const pending = store.refresh(active => {
    signal = active;
    return new Promise<Dashboard>(resolve => { release = resolve; });
  });
  store.cancel();
  assert.equal(signal.aborted, true);
  const before = updates;
  release(empty);
  await pending;
  assert.equal(updates, before);
  assert.equal(store.snapshot, null);
  assert.equal(store.state, "loading");
  await store.refresh(async () => empty);
  assert.equal(store.state, "empty");
});

test("disconnect retains the safe snapshot and does not turn an abort into a failure", async () => {
  const store = new DashboardStore(() => {});
  await store.refresh(async () => empty);
  let reject!: (error: Error) => void;
  const pending = store.refresh(() => new Promise((_, fail) => { reject = fail; }));
  store.cancel();
  reject(new Error("AbortError"));
  await pending;
  assert.equal(store.snapshot, empty);
  assert.notEqual(store.state, "stale");
  assert.notEqual(store.state, "blocked");
});

test("a superseding refresh aborts the previous request without changing the newer result", async () => {
  const store = new DashboardStore(() => {});
  let signal!: AbortSignal;
  let release!: (value: Dashboard) => void;
  const previous = store.refresh(active => {
    signal = active;
    return new Promise<Dashboard>(resolve => { release = resolve; });
  });
  await store.refresh(async () => ({ ...empty, version: "newer" }));
  assert.equal(signal.aborted, true);
  release(empty);
  await previous;
  assert.equal(store.snapshot?.version, "newer");
});
