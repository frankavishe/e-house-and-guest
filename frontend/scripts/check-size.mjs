// Fails if any App Router route ships more than the initial-JS budget (gzip),
// Constitution Principle VI / plan.md: ≤ 300 KB gz per route. Run after `next build`.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const BUDGET_KB = Number(process.env.JS_BUDGET_KB ?? 300);
const nextDir = ".next";

const manifest = JSON.parse(readFileSync(join(nextDir, "app-build-manifest.json"), "utf8"));
const gzCache = new Map();
const gzSize = (file) => {
  if (!gzCache.has(file)) gzCache.set(file, gzipSync(readFileSync(join(nextDir, file))).length);
  return gzCache.get(file);
};

let failed = false;
const rows = [];
for (const [route, files] of Object.entries(manifest.pages)) {
  const js = [...new Set(files.filter((f) => f.endsWith(".js")))];
  const kb = js.reduce((sum, f) => sum + gzSize(f), 0) / 1024;
  const over = kb > BUDGET_KB;
  failed ||= over;
  rows.push({ route, "gz KB": kb.toFixed(1), status: over ? "OVER" : "ok" });
}

console.table(rows);
if (failed) {
  console.error(`One or more routes exceed the ${BUDGET_KB} KB gz JS budget.`);
  process.exit(1);
}
console.log(`All routes within ${BUDGET_KB} KB gz JS budget.`);
