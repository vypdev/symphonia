// Presentation-only sections composed from an already safe dashboard DTO.

import { html } from "lit";
import type { Dashboard, Section, ViewState } from "./model.ts";

export function snapshotStatus(state: ViewState): { label: string; tone: string } | null {
  switch (state) {
    case "ready":
    case "empty": return { label: "Storage ready", tone: "positive" };
    case "refreshing": return { label: "Refreshing", tone: "caution" };
    case "stale": return { label: "Snapshot stale", tone: "caution" };
    default: return null;
  }
}

export function renderLoadState(state: ViewState) {
  switch (state) {
    case "loading": return html`<div class="alert">Loading stored status…</div>`;
    case "refreshing": return html`<div class="alert">Refreshing stored status…</div>`;
    case "blocked": return html`<div class="alert" data-tone="negative"><strong>Status unavailable.</strong><p>Check that the App is running, then retry.</p></div>`;
    case "stale": return html`<div class="alert" data-tone="caution"><strong>Could not refresh.</strong><p>Showing the last successful snapshot. Try again or check App logs.</p></div>`;
    case "empty": return html`<div class="alert" data-tone="caution"><strong>No stored data yet.</strong><p>The App is ready, but no connections, playlists, or operations are recorded.</p></div>`;
    default: return html``;
  }
}

export function dateText(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Not available" : date.toLocaleString();
}

export function stateTone(value: string): string {
  if (["completed", "succeeded", "ready", "active"].includes(value)) return "positive";
  if (["failed", "cancelled", "blocked"].includes(value)) return "negative";
  return "caution";
}

function overview(snapshot: Dashboard) {
  return html`
    <div class="grid">
      <section class="panel"><h2>Operations</h2><p class="metric">${snapshot.queue.total}</p><p class="muted">${snapshot.queue.eligible_count} eligible to run</p></section>
      <section class="panel"><h2>Connections</h2><p class="metric">${snapshot.connections.total}</p><p class="muted">${snapshot.connections.expired_count} expired</p></section>
      <section class="panel"><h2>Library</h2><p class="metric">${snapshot.library.current_playlists}</p><p class="muted">current playlists · ${snapshot.library.entries} entries</p></section>
    </div>
    <section class="panel"><h2>Next steps</h2><p>Provider setup, library import, playback, and playlist copy are not available in this build. This dashboard reflects stored App data only.</p></section>
  `;
}

function connections(snapshot: Dashboard) {
  const providers = Object.entries(snapshot.connections.by_provider);
  return html`<section class="panel"><h2>Stored connections</h2>
    ${providers.length ? providers.map(([provider, states]) => html`<div class="row"><div class="row-copy"><strong>${provider}</strong><small>${Object.entries(states).map(([state, count]) => `${state}: ${count}`).join(" · ")}</small></div></div>`) : html`<p>No connections recorded. Provider setup is not available in this build.</p>`}
    <p class="muted">${snapshot.connections.expired_count} connection records have expired credentials.</p>
  </section>`;
}

function library(snapshot: Dashboard) {
  return html`<section class="panel"><h2>Stored library projection</h2><dl>
    <div class="fact"><dt>Current playlists</dt><dd>${snapshot.library.current_playlists}</dd></div>
    <div class="fact"><dt>Entries</dt><dd>${snapshot.library.entries}</dd></div>
    <div class="fact"><dt>Unavailable entries</dt><dd>${snapshot.library.unavailable_entries}</dd></div>
    <div class="fact"><dt>Last published</dt><dd>${dateText(snapshot.library.latest_published_at)}</dd></div>
  </dl><p class="muted">Import controls are not available in this build.</p></section>`;
}

function activity(snapshot: Dashboard) {
  return html`<section class="panel"><h2>Recent operations</h2>
    ${snapshot.operations.length ? snapshot.operations.map(operation => html`<div class="row">
      <div class="row-copy"><strong>${operation.type || "Operation"}</strong><small>${operation.id} · Updated ${dateText(operation.updated_at)}</small></div>
      <span class="status" data-tone=${stateTone(operation.state)}>${operation.state || "unknown"}</span>
    </div>`) : html`<p>No operations recorded.</p>`}
  </section>`;
}

function diagnostics(snapshot: Dashboard) {
  return html`<section class="panel"><h2>App diagnostics</h2><dl>
    <div class="fact"><dt>Service</dt><dd>Ready</dd></div>
    <div class="fact"><dt>Version</dt><dd>${snapshot.version}</dd></div>
    <div class="fact"><dt>Queue states</dt><dd>${Object.entries(snapshot.queue.states).map(([state, count]) => `${state}: ${count}`).join(" · ") || "None"}</dd></div>
    <div class="fact"><dt>Identity decisions</dt><dd>${snapshot.resolutions.total}</dd></div>
    <div class="fact"><dt>Last successful read</dt><dd>${dateText(snapshot.generated_at)}</dd></div>
  </dl><p class="muted">Detailed payloads, account identifiers, and credentials are never shown here.</p></section>`;
}

export function renderSection(section: Section, snapshot: Dashboard) {
  switch (section) {
    case "connections": return connections(snapshot);
    case "library": return library(snapshot);
    case "activity": return activity(snapshot);
    case "diagnostics": return diagnostics(snapshot);
    default: return overview(snapshot);
  }
}
