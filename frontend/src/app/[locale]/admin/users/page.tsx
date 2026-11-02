import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Pagination } from "@/components/Pagination";
import { UserSuspendActions } from "@/components/UserSuspendActions";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { getAdminUsers } from "@/lib/api/admin";
import { formatDate, formatPhone } from "@/lib/format";
import { cleanParams, getParam, type RawParams } from "@/lib/search";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<RawParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("users"), robots: { index: false } };
}

/** Find a user by phone, name or email and suspend or reinstate them (FR-030). */
export default async function AdminUsersPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const pairs = cleanParams(query);
  const q = getParam(pairs, "q");
  const rawStatus = getParam(pairs, "status");
  const status = rawStatus === "active" || rawStatus === "suspended" ? rawStatus : undefined;
  const page = Math.max(1, Number(getParam(pairs, "page")) || 1);
  const [t, data] = await Promise.all([getTranslations(), getAdminUsers(q, status, page)]);
  const items = data?.items ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.users")} subtitle={t("admin.sub_users")} />
      <form
        method="get"
        role="search"
        className="grid gap-3 rounded-[var(--radius-card)] bg-card p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
      >
        <Input label={t("adminUsers.search")} name="q" defaultValue={q ?? ""} maxLength={50} />
        <Select
          label={t("adminUsers.status")}
          name="status"
          defaultValue={status ?? ""}
          options={[
            { value: "", label: t("adminUsers.all") },
            { value: "active", label: t("adminUsers.status_active") },
            { value: "suspended", label: t("adminUsers.status_suspended") },
          ]}
        />
        <Button type="submit">{t("adminUsers.find")}</Button>
      </form>
      {items.length === 0 ? (
        <EmptyState icon="users">{t("adminUsers.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((u) => (
            <li key={u.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <Avatar name={u.name} />
                <span className="min-w-0 flex-1 truncate font-semibold text-ink">
                  {u.name || formatPhone(u.phone)}
                </span>
                <span className="flex shrink-0 gap-1">
                  {u.is_admin && <Badge tone="brand">{t("adminUsers.admin")}</Badge>}
                  <Badge tone={u.status === "suspended" ? "danger" : "success"}>
                    {t(`adminUsers.status_${u.status}`)}
                  </Badge>
                </span>
              </div>
              <InfoTiles
                tiles={[
                  { label: t("adminUsers.phone"), value: formatPhone(u.phone) },
                  u.email && { label: t("adminUsers.email"), value: u.email },
                  u.owner && { label: t("adminUsers.owner"), value: u.owner.display_name },
                  { label: t("adminUsers.joined"), value: formatDate(u.created_at, locale) },
                ]}
              />
              {!u.is_admin && u.status !== "deleted" && (
                <UserSuspendActions id={u.id} suspended={u.status === "suspended"} />
              )}
            </li>
          ))}
        </ul>
      )}
      {data && (
        <Pagination
          pairs={pairs}
          page={page}
          pageSize={data.page_size}
          total={data.total}
          path="/admin/users"
        />
      )}
    </div>
  );
}
