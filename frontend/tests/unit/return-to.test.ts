import { describe, expect, it } from "vitest";
import { safeReturnTo, withLocale } from "@/lib/returnTo";

describe("withLocale", () => {
  it("adds the locale once", () => {
    expect(withLocale("/", "sw")).toBe("/sw");
    expect(withLocale("/l/1", "en")).toBe("/en/l/1");
    expect(withLocale("/en/l/1", "sw")).toBe("/en/l/1");
  });
});

describe("safeReturnTo", () => {
  it("keeps same-site paths", () => {
    expect(safeReturnTo("/l/123?from=search")).toBe("/l/123?from=search");
    expect(safeReturnTo("/en/book/abc")).toBe("/en/book/abc");
  });
  it("rejects open redirects", () => {
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "", null, undefined]) {
      expect(safeReturnTo(bad)).toBe("/");
    }
  });
});
