// US2 smoke (quickstart V4): a visitor picks dates on an instant-book listing, signs in with
// an SMS code, books, pays with the mock provider and lands on the receipt; the booking then
// shows in "My bookings". Runs at 360×640 against the compose stack (console SMS, mock pay).
import { expect, test } from "@playwright/test";
import { NAV, isoDaysFromNow, otpFor } from "./helpers";

test("book an instant listing and pay with mobile money", async ({ page, request }) => {
  test.setTimeout(120_000);

  // An instant-book, day-priced listing; a random far-off day keeps reruns from colliding.
  const search = await request.get("/api/v1/listings/search?page_size=50");
  const { items } = (await search.json()) as {
    items: { id: string; booking_mode: string; instant_book: boolean }[];
  };
  const listing = items.find((l) => l.booking_mode === "DATE_RANGE" && l.instant_book);
  expect(listing, "seeded instant DATE_RANGE listing").toBeTruthy();
  const day = isoDaysFromNow(60 + Math.floor(Math.random() * 300));

  await page.goto(`/en/l/${listing!.id}?start_date=${day}&end_date=${day}`);
  await expect(page.getByRole("heading", { name: "Book this listing" })).toBeVisible(NAV);
  await expect(page.getByText("Total")).toBeVisible(NAV); // live quote for the prefilled day

  // Sign in from the widget; the dates survive the round trip.
  await page.getByRole("link", { name: "Sign in to book" }).click();
  await expect(page).toHaveURL(/\/en\/account\/sign-in\?returnTo=/, NAV);
  const local = `07${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}`;
  const phone = `+255${local.slice(1)}`;
  await page.getByLabel("Phone number").fill(local);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("SMS code").fill(await otpFor(phone));
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByLabel("Full name").fill("Asha Mteja");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page).toHaveURL(new RegExp(`/en/l/${listing!.id}\\?.*start_date=${day}`), NAV);
  await expect(page.getByText("Total")).toBeVisible(NAV);
  await page.getByRole("button", { name: "Book and pay" }).click();

  // Checkout: M-Pesa, a mock number that succeeds, then poll until confirmed.
  await expect(page).toHaveURL(/\/en\/book\/[0-9a-f-]{36}$/, NAV);
  await expect(page.getByText("Awaiting payment")).toBeVisible();
  await page.getByLabel("M-Pesa").check();
  await page.getByLabel("Paying number").fill("0712000001");
  await page.getByRole("button", { name: /^Pay TSh/ }).click();
  await expect(page.getByText("Check your phone")).toBeVisible();

  await expect(page).toHaveURL(/\/en\/book\/[0-9a-f-]{36}\/receipt$/, NAV);
  await expect(page.getByRole("heading", { name: "Receipt" })).toBeVisible(NAV);
  await expect(page.getByText("Confirmed")).toBeVisible();
  const code = (await page.locator("dt:has-text('Booking code') + dd").textContent())!.trim();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  await page.getByRole("link", { name: "Asha Mteja" }).click();
  await expect(page).toHaveURL(/\/en\/account$/, NAV);
  await page.getByRole("link", { name: /My bookings/ }).click();
  await expect(page).toHaveURL(/\/en\/account\/bookings$/, NAV);
  await expect(page.getByText(code)).toBeVisible();
});
