import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { ClientMessages } from "@/i18n/ClientMessages";
import { redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

/** Admin area: signed-out visitors go to sign-in; signed-in non-admins get a 404. The API
 * enforces the same rule on every admin route. */
export default async function AdminLayout({ children, params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/admin/verifications", locale });
    return null;
  }
  if (!user.roles.includes("admin")) notFound();

  return (
    <ClientMessages section="admin">
      <DashboardShell section="admin">{children}</DashboardShell>
    </ClientMessages>
  );
}
