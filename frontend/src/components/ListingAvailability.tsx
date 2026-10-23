import { getTranslations } from "next-intl/server";
import type { Availability } from "@/lib/api/queries";
import { formatTime } from "@/lib/format";

type Locale = "sw" | "en";

const dateLocale: Record<Locale, string> = { sw: "sw-TZ", en: "en-GB" };
const SW_WEEKDAYS = ["Jtt", "Jnn", "Jtn", "Alh", "Iju", "Jms", "Jpl"];

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function utc(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

/** Monday-first weekday headers (2024-01-01 was a Monday). CLDR's Swahili narrow names are the
 * English letters (M T W …), so Swahili uses the common three-letter abbreviations. */
export function weekdayLabels(locale: Locale): string[] {
  if (locale === "sw") return SW_WEEKDAYS;
  return Array.from({ length: 7 }, (_, i) =>
    dayLabel(addDays("2024-01-01", i), locale, { weekday: "narrow" }),
  );
}

function dayLabel(iso: string, locale: Locale, opts: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(dateLocale[locale], { timeZone: "UTC", ...opts }).format(utc(iso));
}

/** Month grids from `from` for `days` days; unavailable days are struck through. */
function Calendar({
  from,
  days,
  blocked,
  locale,
  legend,
}: {
  from: string;
  days: number;
  blocked: Set<string>;
  locale: Locale;
  legend: { free: string; taken: string };
}) {
  const last = addDays(from, days - 1);
  const months: string[] = [];
  for (let m = from.slice(0, 7); `${m}-01` <= last; m = addDays(`${m}-01`, 32).slice(0, 7)) {
    months.push(m);
  }
  const weekdays = weekdayLabels(locale);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {months.map((month) => {
          const first = `${month}-01`;
          const offset = (utc(first).getUTCDay() + 6) % 7;
          const length = new Date(Date.UTC(+month.slice(0, 4), +month.slice(5, 7), 0)).getUTCDate();
          const cells = Array.from({ length: length }, (_, i) => addDays(first, i));
          return (
            <figure key={month}>
              <figcaption className="mb-1 text-sm font-medium text-ink">
                {dayLabel(first, locale, { month: "long", year: "numeric" })}
              </figcaption>
              <div className="grid grid-cols-7 gap-1 text-center text-xs">
                {weekdays.map((w, i) => (
                  <span key={i} aria-hidden className="text-muted">
                    {w}
                  </span>
                ))}
                {Array.from({ length: offset }, (_, i) => (
                  <span key={`pad-${i}`} />
                ))}
                {cells.map((day) => {
                  const outside = day < from || day > last;
                  const taken = blocked.has(day);
                  return (
                    <span
                      key={day}
                      aria-label={`${dayLabel(day, locale, { day: "numeric", month: "long" })}: ${
                        taken ? legend.taken : legend.free
                      }`}
                      className={`rounded py-1 ${
                        outside
                          ? "text-line"
                          : taken
                            ? "bg-line text-muted line-through"
                            : "bg-brand-50 text-brand-800"
                      }`}
                    >
                      {Number(day.slice(8))}
                    </span>
                  );
                })}
              </div>
            </figure>
          );
        })}
      </div>
      <p className="flex gap-4 text-xs text-muted">
        <span>
          <span aria-hidden className="mr-1 inline-block size-3 rounded bg-brand-50 align-middle" />
          {legend.free}
        </span>
        <span>
          <span aria-hidden className="mr-1 inline-block size-3 rounded bg-line align-middle" />
          {legend.taken}
        </span>
      </p>
    </div>
  );
}

/** Calendar (DATE_RANGE, LEASE), free slots (TIME_SLOT) or units per day (QUANTITY). */
export async function ListingAvailability({
  availability,
  from,
  days,
  locale,
}: {
  availability: Availability | null;
  from: string;
  days: number;
  locale: Locale;
}) {
  const t = await getTranslations("listing");
  if (!availability) return <p className="text-sm text-muted">{t("availabilityUnknown")}</p>;

  if (availability.slots) {
    const open = availability.slots.filter((d) => d.slots.length > 0);
    if (open.length === 0) return <p className="text-sm text-muted">{t("noSlots")}</p>;
    return (
      <ul className="flex flex-col gap-3">
        {open.map((day) => (
          <li key={day.date}>
            <p className="mb-1 text-sm font-medium text-ink">
              {dayLabel(day.date, locale, { weekday: "long", day: "numeric", month: "short" })}
            </p>
            <ul className="flex flex-wrap gap-1">
              {day.slots.map((slot) => (
                <li
                  key={slot.start}
                  className="rounded-md bg-brand-50 px-2 py-1 text-xs tabular-nums text-brand-800"
                >
                  {formatTime(slot.start, locale)}–{formatTime(slot.end, locale)}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    );
  }

  if (availability.stock) {
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 font-medium">{t("date")}</th>
            <th className="py-1 text-right font-medium">{t("available")}</th>
          </tr>
        </thead>
        <tbody>
          {availability.stock.map((d) => (
            <tr key={d.date} className="border-t border-line">
              <td className="py-1">
                {dayLabel(d.date, locale, { weekday: "short", day: "numeric", month: "short" })}
              </td>
              <td
                className={`py-1 text-right tabular-nums ${d.available ? "text-ink" : "text-muted"}`}
              >
                {d.available}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  const blocked = new Set<string>();
  for (const span of availability.unavailable ?? []) {
    for (let d = span.start_date; d < span.end_date; d = addDays(d, 1)) blocked.add(d);
  }
  return (
    <Calendar
      from={from}
      days={days}
      blocked={blocked}
      locale={locale}
      legend={{ free: t("free"), taken: t("taken") }}
    />
  );
}
