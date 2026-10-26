import { getTranslations } from "next-intl/server";
import { Suspense, type ReactNode } from "react";
import { Link } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { formatPhone } from "@/lib/format";
import { Icon } from "../icons";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { NotificationBell } from "../NotificationBell";
import { ThemeToggle } from "../ThemeToggle";
import { Avatar } from "../ui/Avatar";
import { buttonClasses } from "../ui/Button";
import { DashboardFrame } from "./DashboardFrame";
import { Logo } from "./Logo";
import { MobileTabBar } from "./MobileTabBar";
import { SidebarNav, type NavGroup, type NavItem } from "./SidebarNav";

type Section = "account" | "owner" | "admin";

const ADMIN_SECTIONS = [
  ["stats", "chart"],
  ["verifications", "shield"],
  ["listings", "checkCircle"],
  ["bookings", "calendar"],
  ["claims", "scale"],
  ["payouts", "wallet"],
  ["reports", "flag"],
  ["users", "users"],
  ["categories", "tag"],
] as const;

/** Sidebar shell for the signed-in areas, modelled on the reference dashboard: nav on the left,
 * greeting and quick actions on top, the page in the white shell. Bottom tabs on phones. */
export async function DashboardShell({ section, children }: { section: Section; children: ReactNode }) {
  const user = await getCurrentUser();
  // Signed out: the page itself redirects to sign-in.
  if (!user) return <>{children}</>;
  const t = await getTranslations();
  const isOwner = Boolean(user.owner_profile);
  const isAdmin = user.roles.includes("admin");

  const sectionItems: Record<Section, NavItem[]> = {
    account: [
      { href: "/account", label: t("shell.overview"), icon: "home", exact: true },
      { href: "/account/bookings", label: t("account.bookings"), icon: "calendar" },
      { href: "/account/messages", label: t("account.messages"), icon: "message" },
    ],
    owner: [
      { href: "/owner/listings", label: t("ownerNav.listings"), icon: "grid" },
      { href: "/owner/requests", label: t("ownerNav.requests"), icon: "inbox" },
      { href: "/owner/calendar", label: t("ownerNav.calendar"), icon: "calendar" },
      { href: "/owner/earnings", label: t("ownerNav.earnings"), icon: "wallet" },
      { href: "/owner/onboarding", label: t("ownerNav.profile"), icon: "user" },
    ],
    admin: ADMIN_SECTIONS.map(([key, icon]) => ({
      href: `/admin/${key}`,
      label: t(`admin.${key}`),
      icon,
    })),
  };

  // Links to the user's other areas.
  const areas: NavItem[] = [];
  if (section !== "account")
    areas.push({ href: "/account", label: t("shell.renter"), icon: "home", exact: true });
  if (section !== "owner")
    areas.push(
      isOwner
        ? { href: "/owner/listings", label: t("shell.ownerArea"), icon: "building" }
        : { href: "/owner/onboarding", label: t("shell.becomeOwner"), icon: "building" },
    );
  if (isAdmin && section !== "admin")
    areas.push({ href: "/admin/stats", label: t("shell.adminArea"), icon: "shield" });
  areas.push({ href: "/search", label: t("shell.browse"), icon: "search" });

  const groups: NavGroup[] = [
    { items: sectionItems[section] },
    { label: t("shell.sections"), items: areas },
  ];
  const tabs = sectionItems[section].slice(0, 4);
  const more: NavGroup[] = [
    ...(sectionItems[section].length > 4 ? [{ items: sectionItems[section].slice(4) }] : []),
    { label: t("shell.sections"), items: areas },
  ];

  const cta =
    section === "owner" ? (
      <Link href="/owner/listings/new" className={buttonClasses("primary", "md")}>
        <Icon name="plus" className="size-4" />
        <span className="hidden sm:inline">{t("ownerListings.new")}</span>
      </Link>
    ) : section === "account" ? (
      <Link href="/search" className={`${buttonClasses("primary", "md")} hidden sm:inline-flex`}>
        {t("shell.browse")}
      </Link>
    ) : null;

  const iconButton =
    "flex size-10 items-center justify-center rounded-full bg-card text-ink hover:bg-brand-50";

  const sidebar = (
    <div className="flex min-h-full flex-col">
      <Logo name={t("common.appName")} className="mb-8 px-2" />
      <SidebarNav groups={groups} label={t("shell.menu")} />
      <div className="mt-auto flex flex-col gap-4 pt-8">
        <Link href="/account" className="flex items-center gap-3 rounded-2xl px-2 py-1.5 hover:bg-card">
          <Avatar name={user.name} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">
              {user.name ?? t("account.title")}
            </span>
            <span className="block truncate text-xs text-muted">{formatPhone(user.phone)}</span>
          </span>
        </Link>
        <ThemeToggle />
      </div>
    </div>
  );

  const topbar = (
    <header className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 lg:hidden">
        <Logo name={t("common.appName")} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xl font-semibold tracking-tight sm:text-2xl">
            {user.name ? t("shell.greeting", { name: user.name.split(" ")[0] }) : t("shell.greetingAnon")}
          </p>
          <p className="mt-0.5 text-sm text-muted">{t(`shell.subtitle_${section}`)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Suspense fallback={null}>
            <LanguageSwitcher />
          </Suspense>
          <Link href="/search" aria-label={t("shell.search")} title={t("shell.search")} className={iconButton}>
            <Icon name="search" />
          </Link>
          <Link
            href="/account/messages"
            aria-label={t("nav.messages")}
            title={t("nav.messages")}
            className={iconButton}
          >
            <Icon name="message" />
          </Link>
          <NotificationBell />
          {cta}
        </div>
      </div>
    </header>
  );

  return (
    <DashboardFrame
      sidebar={sidebar}
      topbar={topbar}
      tabbar={
        <MobileTabBar
          tabs={tabs}
          more={more}
          label={t("shell.menu")}
          moreLabel={t("shell.more")}
          closeLabel={t("common.close")}
          footer={<ThemeToggle />}
        />
      }
    >
      {children}
    </DashboardFrame>
  );
}
