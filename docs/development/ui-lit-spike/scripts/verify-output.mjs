import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";

const html = readFileSync("dist/index.html", "utf8");
const scripts = [...html.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/g)].map((match) => match[1]);
assert.equal(scripts.length, 1, "one bundled entry asset is expected");
assert.match(scripts[0], /^\.\/assets\/[A-Za-z0-9._-]+\.js$/);
assert.doesNotMatch(html, /(?:src|href)="(?:\/|https?:|\/\/)/, "built asset URLs must remain relative");

const asset = scripts[0].slice(2);
const bytes = readFileSync(`dist/${asset}`);
assert.ok(statSync(`dist/${asset}`).isFile());
console.log(`Spike asset: ${bytes.length} bytes, ${gzipSync(bytes).length} bytes gzip`);
