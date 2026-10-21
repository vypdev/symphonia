import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const browserGlobals = new Set(["fetch", "window", "document", "localStorage", "sessionStorage", "XMLHttpRequest"]);

function* sourceFiles(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    assert.ok(!entry.isSymbolicLink(), `${path} must not be a symlink`);
    if (entry.isDirectory()) yield* sourceFiles(path);
    else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".test.ts")) yield path;
  }
}

for (const file of sourceFiles("src")) {
  const source = readFileSync(file, "utf8");
  const imports = [...source.matchAll(/\bimport\s+(?:[^;]*?\s+from\s+)?["']([^"']+)["']/g)]
    .map(match => match[1]);
  for (const specifier of imports) {
    assert.ok(specifier === "lit" || specifier.startsWith("./"), `${file} imports an outer layer: ${specifier}`);
    assert.ok(!specifier.includes(".."), `${file} escapes the UI package: ${specifier}`);
    if (file === join("src", "views.ts")) {
      assert.ok(specifier === "lit" || specifier === "./model.ts", `${file} imports a non-presentation module`);
    }
  }
  if (file !== join("src", "main.ts")) {
    for (const name of browserGlobals) {
      assert.doesNotMatch(source, new RegExp(`\\b${name}\\b`), `${file} accesses browser I/O: ${name}`);
    }
  }
}
