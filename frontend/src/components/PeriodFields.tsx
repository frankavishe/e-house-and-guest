import { getTranslations } from "next-intl/server";
import { eatDateString } from "@/lib/format";
import { getParam, type Pair } from "@/lib/search";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Mode = "DATE_RANGE" | "TIME_SLOT" | "LEASE" | "QUANTITY";

/** Period inputs for a booking mode (R2), named like the search query (`start_date`, …).
 * Without a mode (no leaf category chosen) it asks for plain from/to dates. */
export async function PeriodFields({
  mode,
  defaultUnit,
  pairs,
}: {
  mode: Mode | null | undefined;
  defaultUnit?: string | null;
  pairs: Pair[];
}) {
  const t = await getTranslations("period");
  const today = eatDateString(new Date());
  const value = (key: string) => getParam(pairs, key) ?? "";
  const date = (name: string, label: string) => (
    <Input
      key={name}
      label={label}
      name={name}
      type="date"
      min={today}
      defaultValue={value(name)}
    />
  );

  switch (mode) {
    case "TIME_SLOT":
      return (
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">{date("slot_date", t("date"))}</div>
          <Input
            label={t("startTime")}
            name="slot_start"
            type="time"
            step={1800}
            defaultValue={value("slot_start")}
          />
          <Input
            label={t("endTime")}
            name="slot_end"
            type="time"
            step={1800}
            defaultValue={value("slot_end")}
          />
        </div>
      );
    case "LEASE":
      return (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("moveIn"))}
          <Select
            label={t("months")}
            name="months"
            placeholder={t("any")}
            defaultValue={value("months")}
            options={[1, 2, 3, 6, 9, 12, 18, 24].map((n) => ({
              value: String(n),
              label: t("monthCount", { count: n }),
            }))}
          />
        </div>
      );
    case "QUANTITY":
      return (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("firstDay"))}
          {date("end_date", t("lastDay"))}
          <Input
            label={t("quantity")}
            name="quantity"
            type="number"
            inputMode="numeric"
            min={1}
            defaultValue={value("quantity")}
          />
        </div>
      );
    case "DATE_RANGE":
      return defaultUnit === "night" ? (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("checkIn"))}
          {date("end_date", t("checkOut"))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("firstDay"))}
          {date("end_date", t("lastDay"))}
        </div>
      );
    default:
      return (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("from"))}
          {date("end_date", t("to"))}
        </div>
      );
  }
}
