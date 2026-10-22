import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import type { ReactNode } from "react";
import { BASE_NAMESPACES, SECTION_NAMESPACES, type Section } from "./client-messages";

/** Provides client components with the base namespaces plus those of `section`. A nested
 * provider replaces its parent's messages, which is why the base set is always included. */
export async function ClientMessages({
  section,
  children,
}: {
  section?: Section;
  children: ReactNode;
}) {
  const all = await getMessages();
  const keep: readonly string[] = [
    ...BASE_NAMESPACES,
    ...(section ? SECTION_NAMESPACES[section] : []),
  ];
  const messages = Object.fromEntries(keep.filter((ns) => ns in all).map((ns) => [ns, all[ns]]));
  return <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>;
}
