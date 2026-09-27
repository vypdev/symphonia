import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

for (const file of readdirSync("src").filter((name) => name.endsWith(".ts") && !name.endsWith(".test.ts"))) {
  const source = readFileSync(`src/${file}`, "utf8");
  const imports = [...source.matchAll(/\b(?:import|export)\s+(?:[^;]*?\s+from\s+)?["']([^"']+)["']/g)]
    .map((match) => match[1]);
  for (const specifier of imports) {
    assert.ok(specifier === "lit" || specifier.startsWith("./"), `${file} imports non-presentation module ${specifier}`);
    assert.ok(!specifier.includes(".."), `${file} escapes its presentation package`);
  }
  assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage)\b|window\.parent/, `${file} crosses the fixture boundary`);
}
