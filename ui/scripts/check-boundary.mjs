import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

const pureModules = new Set(["model.ts", "views.ts", "styles.ts"]);
const browserGlobals = new Set(["fetch", "window", "document", "localStorage", "sessionStorage", "XMLHttpRequest"]);

for (const file of readdirSync("src").filter(name => name.endsWith(".ts") && !name.endsWith(".test.ts"))) {
  const source = readFileSync(`src/${file}`, "utf8");
  const imports = [...source.matchAll(/\bimport\s+(?:[^;]*?\s+from\s+)?["']([^"']+)["']/g)]
    .map(match => match[1]);
  for (const specifier of imports) {
    assert.ok(specifier === "lit" || specifier.startsWith("./"), `${file} imports an outer layer: ${specifier}`);
    assert.ok(!specifier.includes(".."), `${file} escapes the UI package: ${specifier}`);
    if (file === "views.ts") {
      assert.ok(specifier === "lit" || specifier === "./model.ts", `${file} imports a non-presentation module`);
    }
  }
  if (pureModules.has(file)) {
    for (const name of browserGlobals) {
      assert.doesNotMatch(source, new RegExp(`\\b${name}\\b`), `${file} accesses browser I/O: ${name}`);
    }
  }
}
