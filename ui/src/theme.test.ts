import { strict as assert } from "node:assert";
import { test } from "node:test";
import { ThemeState } from "./theme.ts";

test("system preference is followed until the first explicit selection", () => {
  const state = new ThemeState(false);
  assert.equal(state.dark, false);
  state.systemChanged(true);
  assert.equal(state.dark, true);
});

test("an explicit dark choice survives subsequent system changes", () => {
  const state = new ThemeState(false);
  state.toggle();
  for (const systemDark of [true, false, true, false]) {
    state.systemChanged(systemDark);
    assert.equal(state.dark, true);
  }
});

test("an explicit light choice survives system changes and can be toggled again", () => {
  const state = new ThemeState(true);
  state.toggle();
  state.systemChanged(false);
  state.systemChanged(true);
  assert.equal(state.dark, false);
  state.toggle();
  state.systemChanged(false);
  assert.equal(state.dark, true);
});
