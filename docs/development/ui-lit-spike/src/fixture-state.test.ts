import assert from "node:assert/strict";
import { test } from "node:test";
import { sectionFromHash, scenarioLabel, scenarioTone, sections } from "./fixture-state.ts";

test("every review route is reachable through a simple hash", () => {
  for (const section of sections) assert.equal(sectionFromHash(`#/${section}`), section);
});

test("unknown and malformed routes safely return to overview", () => {
  for (const hash of ["", "#", "#/unknown", "#/../copy", "#/copy-extra", "#/COPY"]) {
    assert.equal(sectionFromHash(hash), "overview");
  }
});

test("query and nested route content do not change the selected view", () => {
  assert.equal(sectionFromHash("#/library?token=example"), "library");
  assert.equal(sectionFromHash("#/copy/123"), "copy");
});

test("each scenario has a visible label and semantic tone", () => {
  assert.equal(scenarioLabel("ready"), "Up to date");
  assert.equal(scenarioLabel("partial"), "Partial result");
  assert.equal(scenarioLabel("attention"), "Action required");
  assert.equal(scenarioLabel("offline"), "Unavailable");
  assert.equal(scenarioTone("ready"), "positive");
  assert.equal(scenarioTone("partial"), "caution");
  assert.equal(scenarioTone("attention"), "caution");
  assert.equal(scenarioTone("offline"), "negative");
});
