import { html, type TemplateResult } from "lit";
import { alert, fact, panel, row, status, unavailableAction } from "./primitives.ts";
import { scenarioLabel, scenarioTone, type Scenario, type Section } from "./fixture-state.ts";

const disabledReason = "Review fixture only. No account, player, or App API is connected.";

function heading(title: string, description: string): TemplateResult {
  return html`<div class="page-heading"><div><p class="eyebrow">Music workspace</p><h1 tabindex="-1">${title}</h1><p>${description}</p></div></div>`;
}

function scenarioNotice(scenario: Scenario): TemplateResult {
  const descriptions = {
    ready: "All shown records are invented. The last complete snapshot is available for review.",
    partial: "The latest import ended early. The previous complete snapshot remains visible.",
    attention: "A decision or reconciliation is required. No external action has been inferred.",
    offline: "The source cannot be reached. Previously confirmed data remains visible.",
  };
  return alert(scenarioLabel(scenario), descriptions[scenario], scenarioTone(scenario));
}

function overview(scenario: Scenario): TemplateResult {
  return html`${heading("Overview", "Your library, listening session, and pending work in one place.")}
    ${scenarioNotice(scenario)}
    <div class="metric-grid">
      ${panel("Source", html`<p class="metric">1 connected</p><p class="muted">Spotify · synthetic account</p>`)}
      ${panel("Library", html`<p class="metric">12 playlists</p><p class="muted">Last complete import · 09:14</p>`)}
      ${panel("Needs review", html`<p class="metric">3 occurrences</p><p class="muted">Ambiguous recording matches</p>`)}
    </div>
    ${panel("Continue your work", html`
      ${row("Listening", "Choose an exact source and output before control.", status("No active session", "neutral"))}
      ${row("Match review", "Three playlist occurrences need a decision.", status("Action required", "caution"))}
      ${row("Copy preview", "Inspect omissions and ordering before any write.", status("Preview only", "neutral"))}
    `)}
    <p class="muted">Use the section tabs above to inspect each synthetic journey.</p>`;
}

function listening(scenario: Scenario): TemplateResult {
  return html`${heading("Listening", "Select a playback source, content, and exact output before sending a command.")}
    ${scenarioNotice(scenario)}
    <div class="two-column">
      ${panel("Current selection", html`<dl class="facts">
        ${fact("Source", "Spotify · sample account")}
        ${fact("Content", "Evening mix · playlist")}
        ${fact("Output", "Living room speaker · media_player.living_room")}
      </dl>${unavailableAction("Start playback", disabledReason)}`)}
      ${panel("Now playing", html`${row("No confirmed playback", "Last observation: 09:14 · source may be stale", status("Not confirmed", "caution"))}<p class="muted">Pause, skip, seek, and volume appear only when the selected output reports those capabilities. Commands need a confirmed response and refreshed observation.</p>`) }
    </div>`;
}

function connections(scenario: Scenario): TemplateResult {
  return html`${heading("Connections", "Inspect account access, effective capabilities, and reconnect needs.")}
    ${scenarioNotice(scenario)}
    ${panel("Music services", html`
      ${row("Spotify", "Sample account · token health checked at 09:14", status(scenario === "offline" ? "Unavailable" : "Connected", scenario === "offline" ? "negative" : "positive"))}
      ${row("Apple Music", "No account is configured in this review fixture.", status("Not connected", "neutral"))}
      ${row("YouTube Music", "Community-source capability requires a separate support decision.", status("Undecided", "caution"))}
      <p class="muted">A connection grants only the scopes and capabilities confirmed for that account. Provider type alone never proves playback or write access.</p>
      ${unavailableAction("Connect a service", disabledReason)}
    `)}`;
}

function library(scenario: Scenario): TemplateResult {
  return html`${heading("Library", "Browse the last complete snapshot with provenance and freshness.")}
    ${scenarioNotice(scenario)}
    ${panel("Import state", html`<dl class="facts">
      ${fact("Last complete", "Today 09:14 · 12 playlists · 184 occurrences")}
      ${fact("Latest attempt", scenario === "partial" ? "Today 10:02 · incomplete; retained snapshot" : "Today 09:14 · complete")}
      ${fact("Source", "Spotify · sample account")}
    </dl>${unavailableAction("Refresh library", disabledReason)}`)}
    ${panel("Playlists", html`
      ${row("Evening mix", "24 occurrences · source order retained", status("Available", "positive"))}
      ${row("Sunday records", "16 occurrences · 2 unavailable at source", status("Partial", "caution"))}
      ${row("Archive 2024", "31 occurrences · complete snapshot", status("Available", "positive"))}
    `)}`;
}

function matches(scenario: Scenario): TemplateResult {
  return html`${heading("Matches", "Review recording identity per playlist occurrence before copying.")}
    ${scenarioNotice(scenario)}
    ${panel("Needs a decision", html`
      ${row("02 · Blue in Green", "Miles Davis · source: Kind of Blue · two plausible recordings", status("Ambiguous", "caution"))}
      ${row("07 · Heroes", "David Bowie · live and studio versions differ", status("Ambiguous", "caution"))}
      ${row("11 · Intro", "No stable recording evidence from the source", status("Unmatched", "negative"))}
      <p class="muted">Candidate evidence is scoped to each occurrence. An automatic link needs a conservative, versioned policy; unresolved entries remain explicit.</p>
      ${unavailableAction("Save decision", disabledReason)}
    `)}`;
}

function copy(scenario: Scenario): TemplateResult {
  return html`${heading("Copy playlist", "Review an immutable plan, order, and omissions before authorizing any write.")}
    ${scenarioNotice(scenario)}
    ${panel("Plan preview", html`<dl class="facts">
      ${fact("From", "Evening mix · Spotify")}
      ${fact("To", "Apple Music · destination account not connected")}
      ${fact("Plan", "Synthetic preview · no durable plan or digest")}
      ${fact("Writes", "0 · confirmation unavailable")}
    </dl>${alert("Copy blocked", "Connect and verify the destination, then review non-ready occurrences and a durable plan. No target playlist has been created.", "caution")}`)}
    ${panel("Ordered occurrences", html`
      ${row("01 · So What", "Exact recording candidate · source position 1", status("Ready in example", "positive"))}
      ${row("02 · Blue in Green", "Two plausible recordings · source position 2", status("Decision needed", "caution"))}
      ${row("03 · Flamenco Sketches", "No candidate · source position 3", status("Would be omitted", "negative"))}
      ${unavailableAction("Confirm copy", disabledReason)}
    `)}`;
}

function activity(scenario: Scenario): TemplateResult {
  return html`${heading("Activity", "Follow durable operation facts and recover without guessing external outcomes.")}
    ${scenarioNotice(scenario)}
    ${panel("Recent operations", html`
      ${row("Import · Spotify", "Today 09:14 · complete snapshot retained", status("Confirmed", "positive"))}
      ${row("Import · Spotify", "Today 10:02 · stopped after page 3; prior snapshot retained", status("Partial", "caution"))}
      ${row("Copy · sample plan", "Destination result unknown. Inspect the durable checkpoint before any retry.", status("Unknown outcome", "negative"))}
      <p class="muted">A browser response does not prove an external write. Recovery requires a durable operation record and provider reconciliation.</p>
      ${unavailableAction("Retry operation", disabledReason)}
    `)}`;
}

export function viewFor(section: Section, scenario: Scenario): TemplateResult {
  return {
    overview, listening, connections, library, matches, copy, activity,
  }[section](scenario);
}
