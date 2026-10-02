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

  // Lit installs reactive accessors on the prototype. Emitted class fields
  // shadow those accessors and can leave the entire fixture blank at runtime.
  const properties = source.match(/static properties\s*=\s*\{([\s\S]*?)\n\s*\};/);
  if (properties) {
    const reactive = [...properties[1].matchAll(/^\s*(\w+)\s*:/gm)].map((match) => match[1]);
    for (const name of reactive) {
      assert.match(source, new RegExp(`\\bdeclare\\s+(?:private\\s+)?${name}\\s*:`),
        `${file} reactive field ${name} must use declare and constructor initialization`);
    }
  }
}
