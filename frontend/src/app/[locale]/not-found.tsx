import { getTranslations } from "next-intl/server";
import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";

/** Shown for unknown URLs and for records that don't exist (or aren't the viewer's). */
export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center">
      <p className="text-5xl font-bold text-brand-700">404</p>
      <h1 className="text-xl font-bold text-ink">{t("title")}</h1>
      <p className="text-muted">{t("body")}</p>
      <Link href="/" className={buttonClasses()}>
        {t("home")}
      </Link>
    </div>
  );
}
