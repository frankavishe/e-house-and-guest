// Search URL state (US1). The URL is the single source of truth for filters, so every
// results page is shareable and works without JavaScript.

export type RawParams = Record<string, string | string[] | undefined>;
export type Pair = [string, string];

export const ATTR_PREFIX = "attr.";

/** Keys the search page understands; `attr.*` keys are passed through as well. */
const KNOWN = new Set([
  "category",
  "region",
  "district",
  "ward",
  "q",
  "price_min",
  "price_max",
  "bbox",
  "sort",
  "page",
  "view",
  "start_date",
  "end_date",
  "months",
  "quantity",
  // TIME_SLOT input as a date and two EAT clock times; converted to `start`/`end` for the API.
  "slot_date",
  "slot_start",
  "slot_end",
]);

/** Period inputs carried from results to a listing page. */
export const PERIOD_KEYS = [
  "start_date",
  "end_date",
  "months",
  "quantity",
  "slot_date",
  "slot_start",
  "slot_end",
];

/** Non-empty, known params as ordered pairs (blank form fields are dropped). */
export function cleanParams(raw: RawParams): Pair[] {
  const out: Pair[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (!KNOWN.has(key) && !key.startsWith(ATTR_PREFIX)) continue;
    for (const v of Array.isArray(value) ? value : [value]) {
      const trimmed = v?.trim();
      if (trimmed) out.push([key, trimmed]);
    }
  }
  return out;
}

export function getParam(pairs: Pair[], key: string): string | undefined {
  return pairs.find(([k]) => k === key)?.[1];
}

export function getAll(pairs: Pair[], key: string): string[] {
  return pairs.filter(([k]) => k === key).flatMap(([, v]) => v.split(","));
}

export function toQueryString(pairs: Pair[]): string {
  const qs = new URLSearchParams(pairs).toString();
  return qs ? `?${qs}` : "";
}

/** Replace keys (null removes). Any change other than `page` resets to page 1. */
export function withParams(pairs: Pair[], changes: Record<string, string | null>): string {
  const keys = new Set(Object.keys(changes));
  if (!keys.has("page")) keys.add("page");
  const next: Pair[] = pairs.filter(([k]) => !keys.has(k));
  for (const [key, value] of Object.entries(changes)) {
    if (value !== null && value !== "") next.push([key, value]);
  }
  return toQueryString(next);
}

export function periodQuery(pairs: Pair[]): string {
  return toQueryString(pairs.filter(([k]) => PERIOD_KEYS.includes(k)));
}

function nextDay(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/** EAT (UTC+3, no DST) date + clock time → ISO 8601 with offset. */
export function eatInstant(isoDate: string, time: string): string {
  return `${isoDate}T${time}:00+03:00`;
}

/** Pairs to send to `GET /listings/search`: drops UI-only keys and turns a slot
 * (date + times) into `start`/`end`. An end at or before the start runs past midnight. */
export function toApiPairs(pairs: Pair[]): Pair[] {
  const out = pairs.filter(([k]) => !["view", "slot_date", "slot_start", "slot_end"].includes(k));
  const date = getParam(pairs, "slot_date");
  const start = getParam(pairs, "slot_start");
  const end = getParam(pairs, "slot_end");
  if (date && start && end && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    out.push(["start", eatInstant(date, start)]);
    out.push(["end", eatInstant(end <= start ? nextDay(date) : date, end)]);
  }
  return out;
}

/** True when the visitor gave dates, months or a slot (results then carry totals). */
export function hasPeriod(pairs: Pair[]): boolean {
  return pairs.some(([k]) => PERIOD_KEYS.includes(k) && k !== "quantity");
}
