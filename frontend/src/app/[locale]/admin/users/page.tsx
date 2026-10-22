import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Pagination } from "@/components/Pagination";
import { UserSuspendActions } from "@/components/UserSuspendActions";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
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
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.users")}</h1>
      <form method="get" className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
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
        <p className="rounded-xl border border-line p-4 text-muted">{t("adminUsers.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((u) => (
            <li
              key={u.id}
              className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-ink">{u.name || formatPhone(u.phone)}</span>
                <span className="flex gap-1">
                  {u.is_admin && <Badge tone="brand">{t("adminUsers.admin")}</Badge>}
                  <Badge tone={u.status === "suspended" ? "danger" : "neutral"}>
                    {t(`adminUsers.status_${u.status}`)}
                  </Badge>
                </span>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">{t("adminUsers.phone")}</dt>
                <dd>{formatPhone(u.phone)}</dd>
                {u.email && (
                  <>
                    <dt className="text-muted">{t("adminUsers.email")}</dt>
                    <dd>{u.email}</dd>
                  </>
                )}
                {u.owner && (
                  <>
                    <dt className="text-muted">{t("adminUsers.owner")}</dt>
                    <dd>{u.owner.display_name}</dd>
                  </>
                )}
                <dt className="text-muted">{t("adminUsers.joined")}</dt>
                <dd>{formatDate(u.created_at, locale)}</dd>
              </dl>
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
    </>
  );
}
