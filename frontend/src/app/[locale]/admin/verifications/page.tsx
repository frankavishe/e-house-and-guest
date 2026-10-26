import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdminActions } from "@/components/AdminActions";
import { getVerificationQueue } from "@/lib/api/owner";
import { formatDateTime, formatPhone } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("verifications"), robots: { index: false } };
}

/** Pending owner verifications, oldest first (US7-AS2). */
export default async function AdminVerificationsPage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const [t, queue] = await Promise.all([getTranslations("admin"), getVerificationQueue(1)]);
  const items = queue?.items ?? [];

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("verifications")}</h1>
      {items.length === 0 ? (
        <p className="rounded-3xl bg-card p-4 text-muted">{t("noVerifications")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((v) => (
            <li key={v.id} className="flex flex-col gap-3 rounded-3xl bg-card p-4">
              <div className="flex flex-col gap-1">
                <p className="font-medium text-ink">{v.display_name}</p>
                <p className="text-sm text-muted">
                  {v.user.name} · {formatPhone(v.user.phone)} · {t(`kind_${v.kind}`)}
                </p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  {v.nida_number && (
                    <>
                      <dt className="text-muted">{t("nida")}</dt>
                      <dd className="font-mono">{v.nida_number}</dd>
                    </>
                  )}
                  {v.business_name && (
                    <>
                      <dt className="text-muted">{t("business")}</dt>
                      <dd>{v.business_name}</dd>
                    </>
                  )}
                  {v.brela_reg_no && (
                    <>
                      <dt className="text-muted">{t("brela")}</dt>
                      <dd className="font-mono">{v.brela_reg_no}</dd>
                    </>
                  )}
                  {v.tin && (
                    <>
                      <dt className="text-muted">{t("tin")}</dt>
                      <dd className="font-mono">{v.tin}</dd>
                    </>
                  )}
                  <dt className="text-muted">{t("submitted")}</dt>
                  <dd>{formatDateTime(v.updated_at, locale)}</dd>
                </dl>
                {v.documents.length > 0 && (
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {v.documents.map((d, i) => (
                      <li key={d.key}>
                        <a href={d.url} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">
                          {t("document", { n: i + 1 })}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <AdminActions target={{ kind: "owner", id: v.id }} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
