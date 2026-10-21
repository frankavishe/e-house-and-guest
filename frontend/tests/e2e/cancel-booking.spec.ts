// US5 smoke (quickstart V13): a renter books and pays for the flexible demo room far ahead,
// cancels it from the booking page and sees the full refund on its way. 360×640, compose
// stack (console SMS, mock pay).
import { expect, test } from "@playwright/test";
import { NAV, isoDaysFromNow, newPhone, signIn } from "./helpers";

test("cancel a paid flexible booking and get the refund", async ({ page, request }) => {
  test.setTimeout(180_000);

  // Seeded flexible, instant-book room without a deposit (backend/seed/demo.yaml).
  const search = await request.get("/api/v1/listings/search?q=Msasani&page_size=10");
  const { items } = (await search.json()) as { items: { id: string; instant_book: boolean }[] };
  const listing = items.find((l) => l.instant_book);
  expect(listing, "seeded flexible room").toBeTruthy();
  // Two nights on a random far-off date, so reruns don't collide.
  const offset = 60 + Math.floor(Math.random() * 300);
  const [start, end] = [isoDaysFromNow(offset), isoDaysFromNow(offset + 2)];

  const phone = newPhone();
  await signIn(page, phone.local, "Neema Mteja");
  await page.goto(`/en/l/${listing!.id}?start_date=${start}&end_date=${end}`);
  await expect(page.getByText("Total")).toBeVisible(NAV);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Book and pay" }).click();

  await expect(page).toHaveURL(/\/en\/book\/[0-9a-f-]{36}$/, NAV);
  const bookingUrl = new URL(page.url()).pathname;
  await page.getByLabel("M-Pesa").check();
  await page.getByLabel("Paying number").fill("0712000001");
  await page.getByRole("button", { name: /^Pay TSh/ }).click();
  await expect(page).toHaveURL(/\/receipt$/, NAV);

  await page.goto(bookingUrl);
  await expect(page.getByRole("heading", { name: "Cancel booking" })).toBeVisible(NAV);
  await expect(page.getByText("Cancellation policy: Flexible")).toBeVisible();
  await page.waitForLoadState("networkidle"); // hydrated, so the button has its handler
  await page.getByRole("button", { name: "Cancel this booking" }).click();
  await expect(page.getByText("You get back")).toBeVisible(NAV);
  await page.getByLabel("Reason (optional)").fill("Plans changed");
  await page.getByRole("button", { name: "Yes, cancel" }).click();

  await expect(page.getByText("The renter cancelled this booking.")).toBeVisible(NAV);
  await expect(page.getByText("Reason: Plans changed")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Refunds" })).toBeVisible();
  await expect(page.getByText(/Cancellation ·/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cancel booking" })).toHaveCount(0);
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");
});
