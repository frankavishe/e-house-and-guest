import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { withParams, type Pair } from "@/lib/search";
import { buttonClasses } from "./ui/Button";

/** Previous / next links that keep every other search parameter. */
export async function Pagination({
  pairs,
  page,
  pageSize,
  total,
}: {
  pairs: Pair[];
  page: number;
  pageSize: number;
  total: number;
}) {
  const t = await getTranslations("search");
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const link = (target: number, label: string) => (
    <Link
      href={`/search${withParams(pairs, { page: target === 1 ? null : String(target) })}`}
      className={buttonClasses("secondary")}
      rel={target < page ? "prev" : "next"}
    >
      {label}
    </Link>
  );
  return (
    <nav aria-label={t("pagination")} className="flex items-center justify-between gap-2 pt-4">
      {page > 1 ? link(page - 1, t("previous")) : <span />}
      <span className="text-sm text-muted">{t("pageOf", { page, pages })}</span>
      {page < pages ? link(page + 1, t("next")) : <span />}
    </nav>
  );
}
