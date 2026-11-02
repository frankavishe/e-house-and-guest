import { describe, expect, it } from "vitest";
import {
  eatDateString,
  formatDate,
  formatPeriod,
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

describe("formatPeriod", () => {
  // EAT midnights: 2026-11-02 00:00 EAT = 2026-11-01T21:00Z
  const nov2 = "2026-11-01T21:00:00Z";
  const nov5 = "2026-11-04T21:00:00Z";
  it("shows check-in to check-out for nights", () => {
    expect(formatPeriod({ start: nov2, end: nov5 }, "DATE_RANGE", "night", "en")).toBe(
      "2 Nov 2026 – 5 Nov 2026",
    );
  });
  it("shows the last day for day-based periods (exclusive end)", () => {
    expect(formatPeriod({ start: nov2, end: nov5 }, "QUANTITY", "item_day", "en")).toBe(
      "2 Nov 2026 – 4 Nov 2026",
    );
    expect(
      formatPeriod({ start: nov2, end: "2026-11-02T21:00:00Z" }, "DATE_RANGE", "day", "en"),
    ).toBe("2 Nov 2026");
  });
  it("shows clock times for slots", () => {
    expect(
      formatPeriod(
        { start: "2026-11-02T06:00:00Z", end: "2026-11-02T08:00:00Z" },
        "TIME_SLOT",
        "hour",
        "en",
      ),
    ).toBe("2 Nov 2026, 09:00–11:00");
  });
});
