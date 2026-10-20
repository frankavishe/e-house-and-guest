// US2 smoke (quickstart V4): a visitor picks dates on an instant-book listing, signs in with
// an SMS code, books, pays with the mock provider and lands on the receipt; the booking then
// shows in "My bookings". Runs at 360×640 against the compose stack (console SMS, mock pay).
import { execSync } from "node:child_process";
import { expect, test } from "@playwright/test";

const NAV = { timeout: 30_000 };

function isoDaysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

/** The latest sign-in code sent to `phone`, read from the API's console SMS log. */
async function otpFor(phone: string): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const logs = execSync("docker compose logs api --since 2m", {
      cwd: "..",
      encoding: "utf8",
    });
    const codes = [...logs.matchAll(new RegExp(`\\[sms → \\${phone}\\] \\D*(\\d{6})`, "g"))];
    if (codes.length) return codes[codes.length - 1][1];
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no OTP for ${phone} in the api logs`);
}

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
  await expect(page).toHaveURL(/\/en\/account\/bookings$/, NAV);
  await expect(page.getByText(code)).toBeVisible();
});
