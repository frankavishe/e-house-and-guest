import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";
import { DashboardShell } from "@/components/shell/DashboardShell";
import { ClientMessages } from "@/i18n/ClientMessages";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

/** Sends this section's client message namespaces (src/i18n/client-messages.ts) and draws the
 * dashboard shell. */
export default async function Layout({ children, params }: Props) {
  setRequestLocale((await params).locale);
  return (
    <ClientMessages section="account">
      <DashboardShell section="account">{children}</DashboardShell>
    </ClientMessages>
  );
}
