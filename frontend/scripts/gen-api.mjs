// Generates src/lib/api/schema.d.ts from the backend OpenAPI document.
// `npm run gen:api -- --check` fails if the committed file is out of date (CI gate).
// OPENAPI_URL may be a URL or a local JSON file, e.g. one dumped with
//   cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > openapi.json
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";

const source = process.env.OPENAPI_URL ?? "http://localhost:8000/api/v1/openapi.json";
const target = "src/lib/api/schema.d.ts";
const check = process.argv.includes("--check");

const out = check ? join(tmpdir(), `schema-${process.pid}.d.ts`) : target;
mkdirSync(dirname(out), { recursive: true });
execFileSync(
  process.execPath,
  ["node_modules/openapi-typescript/bin/cli.js", source, "-o", out],
  { stdio: "inherit" },
);

if (check) {
  const fresh = readFileSync(out, "utf8");
  rmSync(out);
  const current = existsSync(target) ? readFileSync(target, "utf8") : "";
  if (fresh.replace(/\r\n/g, "\n") !== current.replace(/\r\n/g, "\n")) {
    console.error(`${target} is out of date. Run \`npm run gen:api\` and commit the result.`);
    process.exit(1);
  }
  console.log(`${target} is up to date.`);
}
