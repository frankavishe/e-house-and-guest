"use client";

import type { ReactNode } from "react";
import { usePathname } from "@/i18n/navigation";
import { isDashboardPath } from "./paths";

/** Lays out the dashboard pieces. Pages under a dashboard section that are public
 * (/account/sign-in) get the page alone; SiteFrame gives them the public header. */
export function DashboardFrame({
  sidebar,
  topbar,
  tabbar,
  children,
}: {
  sidebar: ReactNode;
  topbar: ReactNode;
  tabbar: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  if (!isDashboardPath(pathname)) return <>{children}</>;
  return (
    <div className="min-h-dvh lg:p-4">
      <div className="mx-auto flex min-h-dvh max-w-[1440px] bg-surface lg:min-h-[calc(100dvh-2rem)] lg:rounded-[var(--radius-shell)] lg:shadow-soft">
        <aside className="sticky top-4 hidden h-[calc(100dvh-2rem)] w-64 shrink-0 flex-col overflow-y-auto p-5 [scrollbar-width:thin] lg:flex">
          {sidebar}
        </aside>
        <div className="flex min-w-0 flex-1 flex-col gap-6 px-4 pb-28 pt-4 sm:px-6 lg:pb-8 lg:pl-3 lg:pr-8 lg:pt-6">
          {topbar}
          <main id="main" className="flex min-w-0 flex-col gap-6">
            {children}
          </main>
        </div>
      </div>
      {tabbar}
    </div>
  );
}
