import { strict as assert } from "node:assert";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

const script = fileURLToPath(new URL("../scripts/check-boundary.mjs", import.meta.url));
const fixtures: Record<string, string> = {
  pure: "export const value = 1;",
  browser: 'fetch("/unsafe");',
  outer: 'import "provider-sdk";',
  symlink: "export const value = 1;",
  dynamicLocal: 'void import("./local.ts");',
  dynamicOuter: 'void import /* comment */ ("provider-sdk");',
  dynamicEscape: 'void import("../../outside.ts");',
  templateEscape: 'void import(`../../outside.ts`);',
  computed: 'const name = "./local.ts"; void import(name);',
  reexport: 'export { value } from "provider-sdk";',
  typeImport: 'export type Value = import("provider-sdk").Value;',
};

for (const [kind, source] of Object.entries(fixtures)) {
  test(`boundary fixture: ${kind}`, () => {
    const root = mkdtempSync(join(tmpdir(), "symphonia-boundary-"));
    try {
      mkdirSync(join(root, "src/nested"), { recursive: true });
      writeFileSync(join(root, "src/main.ts"), 'import "./nested/helper.ts";');
      writeFileSync(join(root, "src/nested/helper.ts"), source);
      writeFileSync(join(root, "src/nested/local.ts"), "export const value = 1;");
      if (kind === "symlink") {
        writeFileSync(join(root, "outside.ts"), "export const value = 1;");
        symlinkSync(join(root, "outside.ts"), join(root, "src/escape.ts"));
      }
      const result = spawnSync(process.execPath, [script], { cwd: root, encoding: "utf8", timeout: 10_000 });
      assert.equal(result.error, undefined);
      assert.equal(result.status === 0, kind === "pure" || kind === "dynamicLocal", result.stdout + result.stderr);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
}
