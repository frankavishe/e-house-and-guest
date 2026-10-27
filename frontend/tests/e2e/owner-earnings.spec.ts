// US4 smoke: a new owner opens Earnings (empty totals), adds an M-Pesa payout method that
// becomes the default, and an admin opens the payouts queue and its status filters. 360×640.
import { expect, test } from "@playwright/test";
import { NAV, newPhone, signIn } from "./helpers";

const ADMIN_PHONE = "0774861380"; // seeded admin (backend/seed/demo.yaml)

test("owner sets a payout method on the earnings page; admin sees the payouts queue", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const phone = newPhone();
  await signIn(page, phone.local, "Juma Owner");
  await page.goto("/en/owner/onboarding");
  await page.getByLabel("Public name").fill(`Juma Rentals ${Date.now().toString(36)}`);
  await page.getByLabel("NIDA number").fill("19900101123450000124");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Not submitted")).toBeVisible(NAV);

  await page.goto("/en/owner/earnings");
  await expect(page.getByRole("heading", { level: 1, name: "Earnings" })).toBeVisible(NAV);
  await expect(page.getByRole("link", { name: "Earnings" })).toHaveAttribute("aria-current", "page");
  await page.waitForLoadState("networkidle"); // hydrated, so the form has its handler
  await expect(page.getByText("No paid bookings in this period yet.")).toBeVisible();
  await expect(page.getByText("Add where we should send your money")).toBeVisible();

  await page.getByLabel("Network").selectOption("mpesa");
  await page.getByLabel("Mobile money number").fill(phone.local);
  await page.getByLabel("Account name").fill("Juma Owner");
  await page.getByRole("button", { name: "Save" }).click();
  const method = page.getByRole("listitem").filter({ hasText: "M-Pesa" });
  await expect(method).toBeVisible(NAV);
  await expect(method.getByText("Default")).toBeVisible();
  await expect(page.getByText("Add where we should send your money")).toHaveCount(0);
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  await page.context().clearCookies(); // sign out the owner
  await signIn(page, ADMIN_PHONE);
  await page.goto("/en/admin/payouts");
  await expect(page.getByRole("heading", { level: 1, name: "Payouts" })).toBeVisible(NAV);
  await page.getByRole("link", { name: "Payout failed" }).click();
  await expect(page).toHaveURL(/status=failed/, NAV);
  await expect(page.getByRole("link", { name: "Payout failed" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
