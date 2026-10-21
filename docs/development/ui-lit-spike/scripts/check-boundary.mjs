import assert from "node:assert/strict";
import { parseSync, Visitor } from "rolldown/utils";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

function* sourceFiles(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    assert.ok(!entry.isSymbolicLink(), `${path} must not be a symlink`);
    if (entry.isDirectory()) yield* sourceFiles(path);
    else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".test.ts")) yield path;
  }
}


function moduleSpecifiers(source, file) {
  const parsed = parseSync(file, source);
  assert.equal(parsed.errors.length, 0, `${file} has invalid TypeScript syntax`);
  const imports = [];
  const add = (node) => {
    if (node?.type === "Literal" && typeof node.value === "string") imports.push(node.value);
    else if (node?.type === "TemplateLiteral" && node.expressions.length === 0) imports.push(node.quasis[0].value.cooked);
    else assert.fail(`${file} has a computed module specifier`);
  };
  new Visitor({
    ImportDeclaration(node) { add(node.source); },
    ExportNamedDeclaration(node) { if (node.source) add(node.source); },
    ExportAllDeclaration(node) { add(node.source); },
    ImportExpression(node) { add(node.source); },
    TSImportType(node) { add(node.source); },
    TSImportEqualsDeclaration(node) {
      assert.equal(node.moduleReference.type, "TSExternalModuleReference", `${file} has an unsupported import alias`);
      add(node.moduleReference.expression);
    },
  }).visit(parsed.program);
  return imports;
}


for (const file of sourceFiles("src")) {
  const source = readFileSync(file, "utf8");
  const imports = moduleSpecifiers(source, file);
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
