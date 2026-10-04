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
