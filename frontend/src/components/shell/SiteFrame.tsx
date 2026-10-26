"use client";

import type { ReactNode } from "react";
import { usePathname } from "@/i18n/navigation";
import { isDashboardPath } from "./paths";

/** Public pages sit in a white rounded shell on the lilac canvas, with the site header and
 * footer. Dashboard routes draw their own shell (DashboardShell), so they get the page alone. */
export function SiteFrame({
  header,
  footer,
  children,
}: {
  header: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  if (isDashboardPath(pathname)) return <>{children}</>;
  return (
    <>
      <div className="sm:px-4 sm:pt-4">
        <div className="mx-auto min-h-[70dvh] max-w-6xl bg-surface shadow-soft sm:rounded-[var(--radius-shell)]">
          {header}
          <main id="main" className="px-4 pb-10 pt-4 sm:px-6 lg:px-8">
            {children}
          </main>
        </div>
      </div>
      {footer}
    </>
  );
}
