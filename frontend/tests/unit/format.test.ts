import { describe, expect, it } from "vitest";
import {
  eatDateString,
  formatDate,
  formatPhone,
  formatTZS,
  formatTime,
  localized,
} from "@/lib/format";

describe("formatTZS", () => {
  it("groups thousands without decimals", () => {
    expect(formatTZS(1250000)).toBe("TSh 1,250,000");
    expect(formatTZS(500)).toBe("TSh 500");
    expect(formatTZS(0)).toBe("TSh 0");
  });
  it("handles negatives (refunds)", () => {
    expect(formatTZS(-20000)).toBe("-TSh 20,000");
  });
});

describe("dates in EAT", () => {
  // 21:30 UTC on 1 Nov is 00:30 on 2 Nov in Dar es Salaam (UTC+3).
  const lateUtc = "2026-11-01T21:30:00Z";

  it("uses the EAT calendar day", () => {
    expect(eatDateString(lateUtc)).toBe("2026-11-02");
    expect(formatDate(lateUtc, "en")).toBe("2 Nov 2026");
  });
  it("formats 24-hour EAT time", () => {
    expect(formatTime(lateUtc, "en")).toBe("00:30");
    expect(formatTime("2026-11-02T06:00:00Z", "sw")).toBe("09:00");
  });
  it("renders Swahili dates", () => {
    expect(formatDate("2026-11-02T06:00:00Z", "sw")).toMatch(/2026/);
  });
});

describe("localized", () => {
  it("prefers the requested language and falls back", () => {
    expect(localized({ sw: "Chumba", en: "Room" }, "en")).toBe("Room");
    expect(localized({ sw: "Chumba", en: null }, "en")).toBe("Chumba");
    expect(localized({ sw: "", en: "Room" }, "sw")).toBe("Room");
    expect(localized(null, "sw")).toBe("");
  });
});

describe("formatPhone", () => {
  it("shows the local format", () => {
    expect(formatPhone("+255712345678")).toBe("0712 345 678");
    expect(formatPhone("weird")).toBe("weird");
  });
});
