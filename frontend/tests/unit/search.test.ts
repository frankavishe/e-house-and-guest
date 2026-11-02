import { describe, expect, it } from "vitest";
import { cleanParams, getAll, hasPeriod, periodQuery, toApiPairs, withParams } from "@/lib/search";

describe("search URL state", () => {
  it("drops blanks and unknown keys, keeps attr.* and repeats", () => {
    const pairs = cleanParams({
      q: " tent ",
      region: "",
      utm_source: "x",
      "attr.kind": ["flat", "hut"],
      "attr.view": "",
    });
    expect(pairs).toEqual([
      ["q", "tent"],
      ["attr.kind", "flat"],
      ["attr.kind", "hut"],
    ]);
    expect(getAll(pairs, "attr.kind")).toEqual(["flat", "hut"]);
  });

  it("resets the page when filters change", () => {
    const pairs = cleanParams({ q: "room", page: "3", sort: "newest" });
    expect(withParams(pairs, { sort: "price_asc" })).toBe("?q=room&sort=price_asc");
    expect(withParams(pairs, { page: "4" })).toBe("?q=room&sort=newest&page=4");
    expect(withParams(pairs, { q: null, sort: null })).toBe("");
  });

  it("carries only the period to listing pages", () => {
    const pairs = cleanParams({ q: "x", start_date: "2026-11-10", end_date: "2026-11-12" });
    expect(periodQuery(pairs)).toBe("?start_date=2026-11-10&end_date=2026-11-12");
    expect(hasPeriod(pairs)).toBe(true);
    expect(hasPeriod(cleanParams({ quantity: "3" }))).toBe(false);
  });

  it("turns a slot into EAT instants, crossing midnight", () => {
    const pairs = cleanParams({
      view: "map",
      slot_date: "2026-12-31",
      slot_start: "20:00",
      slot_end: "02:00",
    });
    expect(toApiPairs(pairs)).toEqual([
      ["start", "2026-12-31T20:00:00+03:00"],
      ["end", "2027-01-01T02:00:00+03:00"],
    ]);
  });
});
