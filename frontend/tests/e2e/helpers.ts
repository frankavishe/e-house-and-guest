// Shared e2e helpers. The compose stack sends SMS to the API's console log (dev OTPs) and
// runs `next dev`, which compiles a route on its first visit (hence the long timeouts).
import { execSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";

export const NAV = { timeout: 30_000 };

export function isoDaysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

/** A fresh local mobile number (07xxxxxxxx) and its E.164 form. */
export function newPhone(): { local: string; e164: string } {
  const local = `07${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}`;
  return { local, e164: `+255${local.slice(1)}` };
}

/** The latest sign-in code sent to `phone`, read from the API's console SMS log. */
export async function otpFor(phone: string): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const logs = execSync("docker compose logs api --since 2m", { cwd: "..", encoding: "utf8" });
    const codes = [...logs.matchAll(new RegExp(`\\[sms → \\${phone}\\] \\D*(\\d{6})`, "g"))];
    if (codes.length) return codes[codes.length - 1][1];
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no OTP for ${phone} in the api logs`);
}

/** Sign in on the English sign-in page; `name` is asked for new users only. */
export async function signIn(page: Page, local: string, name?: string): Promise<void> {
  const e164 = `+255${local.slice(1)}`;
  await page.goto("/en/account/sign-in");
  await page.getByLabel("Phone number").fill(local);
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("SMS code").fill(await otpFor(e164));
  await page.getByRole("button", { name: "Verify" }).click();
  if (name) {
    await page.getByLabel("Full name").fill(name);
    await page.getByRole("button", { name: "Save" }).click();
  }
  await expect(page).toHaveURL(/\/en$/, NAV);
}
