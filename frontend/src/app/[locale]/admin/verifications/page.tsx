import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdminActions } from "@/components/AdminActions";
import { Icon } from "@/components/icons";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("verifications")} subtitle={t("sub_verifications")} />
      {items.length === 0 ? (
        <EmptyState icon="shield">{t("noVerifications")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((v) => (
            <li key={v.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <Avatar name={v.display_name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink">{v.display_name}</p>
                  <p className="truncate text-sm text-muted">
                    {v.user.name} · {formatPhone(v.user.phone)}
                  </p>
                </div>
                <Badge tone="brand">{t(`kind_${v.kind}`)}</Badge>
              </div>
              <InfoTiles
                tiles={[
                  v.nida_number && { label: t("nida"), value: v.nida_number, mono: true },
                  v.business_name && { label: t("business"), value: v.business_name },
                  v.brela_reg_no && { label: t("brela"), value: v.brela_reg_no, mono: true },
                  v.tin && { label: t("tin"), value: v.tin, mono: true },
                  { label: t("submitted"), value: formatDateTime(v.updated_at, locale) },
                ]}
              />
              {v.documents.length > 0 && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs font-medium text-muted">{t("documents")}</p>
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {v.documents.map((d, i) => (
                      <li key={d.key}>
                        <a
                          href={d.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 font-medium text-brand-700 hover:bg-brand-50"
                        >
                          <Icon name="card" className="size-4" />
                          {t("document", { n: i + 1 })}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <AdminActions target={{ kind: "owner", id: v.id }} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
