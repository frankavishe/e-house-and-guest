// SC-007: Swahili and English catalogs must have exactly the same keys and placeholders.
import { describe, expect, it } from "vitest";
import en from "../../messages/en.json";
import sw from "../../messages/sw.json";

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ""): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((acc, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") acc[path] = value;
    else Object.assign(acc, flatten(value, path));
    return acc;
  }, {});
}

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort();

describe("i18n parity", () => {
  const flatSw = flatten(sw as Tree);
  const flatEn = flatten(en as Tree);

  it("has the same keys in sw and en", () => {
    expect(Object.keys(flatSw).sort()).toEqual(Object.keys(flatEn).sort());
  });

  it("has no empty strings", () => {
    for (const [key, value] of [...Object.entries(flatSw), ...Object.entries(flatEn)]) {
      expect(value.trim(), key).not.toBe("");
    }
  });

  it("uses the same placeholders in both languages", () => {
    for (const key of Object.keys(flatSw)) {
      expect(placeholders(flatSw[key]), key).toEqual(placeholders(flatEn[key] ?? ""));
    }
  });
});
