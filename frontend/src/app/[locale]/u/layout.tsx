import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";
import { ClientMessages } from "@/i18n/ClientMessages";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

/** Sends this section's client message namespaces (src/i18n/client-messages.ts). */
export default async function Layout({ children, params }: Props) {
  setRequestLocale((await params).locale);
  return <ClientMessages section="u">{children}</ClientMessages>;
}
