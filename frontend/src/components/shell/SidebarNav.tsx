"use client";

import { Link, usePathname } from "@/i18n/navigation";
import { Icon, type IconName } from "../icons";
import { isCurrent } from "./paths";

export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  /** Only highlight on this exact path (e.g. an overview page above its sub-pages). */
  exact?: boolean;
  badge?: number;
};

export type NavGroup = { label?: string; items: NavItem[] };

/** Sidebar links; the current page is a violet pill with a chevron. */
export function SidebarNav({ groups, label }: { groups: NavGroup[]; label: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="flex flex-col gap-6">
      {groups.map((group, g) => (
        <div key={g} className="flex flex-col gap-1">
          {group.label && (
            <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">
              {group.label}
            </p>
          )}
          {group.items.map((item) => (
            <NavLink key={item.href} item={item} current={isCurrent(pathname, item.href, item.exact)} />
          ))}
        </div>
      ))}
    </nav>
  );
}

export function NavLink({ item, current, onClick }: { item: NavItem; current: boolean; onClick?: () => void }) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={current ? "page" : undefined}
      className={`group flex items-center gap-3 rounded-full px-3 py-2.5 text-sm font-medium transition-colors ${
        current ? "bg-brand-600 text-white shadow-soft" : "text-ink hover:bg-card"
      }`}
    >
      <Icon name={item.icon} className="size-[18px] shrink-0" />
      <span className="truncate">{item.label}</span>
      {item.badge ? (
        <span
          className={`ml-auto flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-semibold leading-5 ${
            current ? "bg-white text-brand-600" : "bg-brand-600 text-white"
          }`}
        >
          {item.badge}
        </span>
      ) : current ? (
        <Icon name="chevronRight" className="ml-auto size-4" />
      ) : null}
    </Link>
  );
}
