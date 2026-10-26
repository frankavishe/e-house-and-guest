"use client";

import { useState, type ReactNode } from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { Icon } from "../icons";
import { Sheet } from "../ui/Sheet";
import { isCurrent } from "./paths";
import { NavLink, type NavGroup, type NavItem } from "./SidebarNav";

/** Bottom tab bar on phones: the first section links, plus "More" for the rest. */
export function MobileTabBar({
  tabs,
  more,
  label,
  moreLabel,
  closeLabel,
  footer,
}: {
  tabs: NavItem[];
  more: NavGroup[];
  label: string;
  moreLabel: string;
  closeLabel: string;
  /** Extra content at the bottom of the "More" sheet (theme switch). */
  footer?: ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const moreCurrent = more.some((g) => g.items.some((i) => isCurrent(pathname, i.href, i.exact)));
  const tabClass = (current: boolean) =>
    `relative flex flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[11px] font-medium ${
      current ? "text-brand-700" : "text-muted"
    }`;

  return (
    <>
      <nav
        aria-label={label}
        className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5 backdrop-blur lg:hidden"
      >
        <div className="mx-auto flex max-w-md items-stretch gap-1">
          {tabs.map((item) => {
            const current = isCurrent(pathname, item.href, item.exact);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={tabClass(current)}
              >
                <span
                  className={`flex h-7 w-12 items-center justify-center rounded-full ${
                    current ? "bg-brand-100" : ""
                  }`}
                >
                  <Icon name={item.icon} className="size-5" />
                </span>
                <span className="max-w-full truncate">{item.label}</span>
                {item.badge ? (
                  <span className="absolute right-[calc(50%-1.25rem)] top-0.5 min-w-4 rounded-full bg-brand-600 px-1 text-[10px] font-bold leading-4 text-white">
                    {item.badge}
                  </span>
                ) : null}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-haspopup="dialog"
            className={tabClass(moreCurrent)}
          >
            <span
              className={`flex h-7 w-12 items-center justify-center rounded-full ${
                moreCurrent ? "bg-brand-100" : ""
              }`}
            >
              <Icon name="more" className="size-5" />
            </span>
            <span>{moreLabel}</span>
          </button>
        </div>
      </nav>
      <Sheet open={open} onClose={() => setOpen(false)} title={moreLabel} closeLabel={closeLabel}>
        <div className="flex flex-col gap-5">
          {more.map((group, g) => (
            <div key={g} className="flex flex-col gap-1">
              {group.label && (
                <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-muted">
                  {group.label}
                </p>
              )}
              {group.items.map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  current={isCurrent(pathname, item.href, item.exact)}
                  onClick={() => setOpen(false)}
                />
              ))}
            </div>
          ))}
          {footer}
        </div>
      </Sheet>
    </>
  );
}
