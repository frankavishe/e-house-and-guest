// Every client component must find its message namespaces in what its route sends to the
// browser (src/i18n/client-messages.ts). Walks each page's and layout's import graph, reads the
// namespaces the client components it reaches use, and compares.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { BASE_NAMESPACES, SECTION_NAMESPACES } from "@/i18n/client-messages";

const SRC = join(__dirname, "../../src");
const APP = join(SRC, "app/[locale]");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function resolveImport(spec: string, from: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = join(SRC, spec.slice(2));
  else if (spec.startsWith(".")) base = join(dirname(from), spec);
  else return null;
  for (const ext of [".tsx", ".ts", "/index.tsx", "/index.ts"]) {
    if (existsSync(base + ext)) return base + ext;
  }
  return null;
}

/** Namespaces a module reads: `useTranslations("ns")`, or `t("ns.key")` when `t` comes from an
 * unscoped `useTranslations()`. A declaration covers the text up to the next declaration of the
 * same name (one file can have several components, each with its own `t`). */
function namespacesOf(source: string): string[] {
  const found = new Set<string>();
  const decls = [
    ...source.matchAll(/const (\w+) = useTranslations\(\s*(?:["'`]([a-zA-Z]+)[."'`])?/g),
  ];
  decls.forEach((decl, i) => {
    const [, name, scope] = decl;
    if (scope) return void found.add(scope);
    const next = decls.slice(i + 1).find((d) => d[1] === name);
    const region = source.slice(decl.index, next?.index);
    const call = new RegExp(`\\b${name}(?:\\.\\w+)?\\(\\s*["'\`]([a-zA-Z]+)\\.`, "g");
    for (const [, ns] of region.matchAll(call)) found.add(ns);
  });
  return [...found];
}

/** Namespaces used by client code reachable from `entry`. A module is client code when it says
 * "use client" or is imported from client code (e.g. ListingStatusBadge inside ListingWizard). */
function clientNamespaces(entry: string): Map<string, string[]> {
  const seen = new Set<string>();
  const stack: [string, boolean][] = [[entry, false]];
  const byComponent = new Map<string, string[]>();
  while (stack.length) {
    const [file, parentIsClient] = stack.pop()!;
    const source = readFileSync(file, "utf8");
    const isClient = parentIsClient || source.startsWith('"use client"');
    const key = `${file}:${isClient}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const used = isClient ? namespacesOf(source) : [];
    if (used.length) byComponent.set(relative(SRC, file), used);
    for (const [, spec] of source.matchAll(/(?:from|import\()\s*["']([^"']+)["']/g)) {
      const dep = resolveImport(spec, file);
      if (dep) stack.push([dep, isClient]);
    }
  }
  return byComponent;
}

const entries = walk(APP).filter((f) => /[\\/](page|layout)\.tsx$/.test(f));
const sections = SECTION_NAMESPACES as Record<string, readonly string[]>;

describe("client message namespaces", () => {
  it.each(entries.map((f) => [relative(APP, f).replaceAll("\\", "/"), f]))(
    "%s gets every namespace its client components use",
    (route, file) => {
      const section = route.split("/")[0];
      const sent = new Set<string>([...BASE_NAMESPACES, ...(sections[section] ?? [])]);
      const missing = [...clientNamespaces(file)].flatMap(([component, used]) =>
        used.filter((ns) => !sent.has(ns)).map((ns) => `${component}: ${ns}`),
      );
      expect(missing).toEqual([]);
    },
  );

  it.each(Object.keys(SECTION_NAMESPACES))("%s/layout.tsx sends its section", (section) => {
    const layout = readFileSync(join(APP, section, "layout.tsx"), "utf8");
    expect(layout).toContain(`<ClientMessages section="${section}">`);
  });

  it("finds the client components (sanity check of the parser)", () => {
    const used = clientNamespaces(join(APP, "l/[id]/page.tsx"));
    expect(used.get(join("components", "BookingWidget.tsx"))).toEqual(
      expect.arrayContaining(["booking", "units", "period", "errors"]),
    );
  });
});
