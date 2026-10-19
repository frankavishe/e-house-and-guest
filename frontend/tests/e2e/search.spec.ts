// US1 smoke (quickstart V1–V3): a signed-out visitor searches by region and dates, opens a
// listing, and switching language keeps the page. Runs at 360×640 (playwright.config.ts).
import { expect, test } from "@playwright/test";

// The compose stack runs `next dev`, which compiles a route on its first visit.
const NAV = { timeout: 30_000 };

function isoDaysFromNow(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return d.toISOString().slice(0, 10);
}

test("search → open listing → switch language keeps the page", async ({ page }) => {
  await page.goto("/sw");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.getByLabel("Mkoa").selectOption({ label: "Dar es Salaam" });
  await page.getByLabel("Kuanzia").fill(isoDaysFromNow(30));
  await page.getByLabel("Hadi").fill(isoDaysFromNow(33));
  await page.getByRole("button", { name: "Tafuta" }).click();

  await expect(page).toHaveURL(/\/sw\/search\?/, NAV);
  expect(page.url()).toContain("region=");
  expect(page.url()).not.toContain("q=&"); // blank fields stay out of the URL
  const cards = page.locator("main article");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first()).toContainText("TSh");
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  await cards.first().getByRole("link").click();
  await expect(page).toHaveURL(/\/sw\/l\/[0-9a-f-]{36}/, NAV);
  const listingPath = new URL(page.url()).pathname.replace(/^\/sw/, "");
  await expect(page.getByRole("heading", { name: "Upatikanaji" })).toBeVisible();

  await page.getByRole("link", { name: "Badili lugha kuwa Kiingereza" }).click();
  await expect(page).toHaveURL(new RegExp(`/en${listingPath}`), NAV);
  await expect(page.getByRole("heading", { name: "Availability" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("category filters come from the category schema", async ({ page }) => {
  await page.goto("/en/search?category=cars");
  await page.getByRole("button", { name: "Filters" }).click();
  const dialog = page.getByRole("dialog", { name: "Filters" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("First day")).toBeVisible(); // cars count days, not nights
  await dialog.getByRole("button", { name: "Show results" }).click();
  await expect(page).toHaveURL(/category=cars/, NAV);
  await expect(page.locator("main article").first()).toBeVisible();
});
