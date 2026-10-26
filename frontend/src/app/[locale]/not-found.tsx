import { getTranslations } from "next-intl/server";
import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";

/** Shown for unknown URLs and for records that don't exist (or aren't the viewer's). */
export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <div className="mx-auto my-6 flex max-w-md flex-col items-center gap-3 rounded-[var(--radius-card)] bg-card px-6 py-12 text-center sm:my-12">
      <p className="bg-gradient-to-br from-brand-400 to-brand-700 bg-clip-text text-7xl font-semibold tracking-tight text-transparent">
        404
      </p>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("title")}</h1>
      <p className="text-muted">{t("body")}</p>
      <Link href="/" className={buttonClasses()}>
        {t("home")}
      </Link>
    </div>
  );
}
