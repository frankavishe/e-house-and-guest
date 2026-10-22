import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { DeleteAccount } from "@/components/DeleteAccount";
import { Link, redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { formatPhone } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("title"), robots: { index: false } };
}

/** The signed-in user's hub: bookings, the owner area (or becoming an owner), admin. */
export default async function AccountPage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/account", locale });
    return null;
  }
  const t = await getTranslations("account");
  const links: [string, string, string][] = [
    ["/account/bookings", t("bookings"), t("bookingsHint")],
    ["/account/messages", t("messages"), t("messagesHint")],
    user.owner_profile
      ? ["/owner/listings", t("ownerArea"), t("ownerAreaHint")]
      : ["/owner/onboarding", t("becomeOwner"), t("becomeOwnerHint")],
  ];
  if (user.owner_profile) links.push(["/owner/requests", t("requests"), t("requestsHint")]);
  if (user.roles.includes("admin"))
    links.push(["/admin/verifications", t("admin"), t("adminHint")]);

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-ink">{user.name ?? t("title")}</h1>
        <p className="text-sm text-muted">{formatPhone(user.phone)}</p>
      </header>
      <ul className="flex flex-col gap-2">
        {links.map(([href, label, hint]) => (
          <li key={href}>
            <Link
              href={href}
              className="flex flex-col rounded-xl border border-line bg-surface p-4 hover:border-brand-600"
            >
              <span className="font-medium text-ink">{label}</span>
              <span className="text-sm text-muted">{hint}</span>
            </Link>
          </li>
        ))}
      </ul>
      <DeleteAccount />
    </div>
  );
}
