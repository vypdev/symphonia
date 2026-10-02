import assert from "node:assert/strict";
import test from "node:test";
import { resolveTheme } from "./appearance.ts";

test("auto follows the browser light preference", () => {
  assert.equal(resolveTheme("auto", false), "light");
});

test("auto follows the browser dark preference", () => {
  assert.equal(resolveTheme("auto", true), "dark");
});

test("an explicit preference does not depend on the browser", () => {
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
});
