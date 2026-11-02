// US3 smoke (quickstart V10): a new owner registers, an admin verifies them, the owner
// creates a warehouse listing (fields come from the category schema), uploads a photo to
// object storage and submits; once an admin approves it, it appears in search. 360×640.
import { expect, test, type Page } from "@playwright/test";
import { NAV, newPhone, signIn } from "./helpers";

const ADMIN_PHONE = "0774861380"; // seeded admin (backend/seed/demo.yaml)

// 1×1 PNG: enough for the upload, confirm and image job.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

async function approveIn(admin: Page, path: string, rowText: string): Promise<void> {
  await admin.goto(path);
  await admin.waitForLoadState("networkidle"); // hydrated, so the button has its handler
  const row = admin.getByRole("listitem").filter({ hasText: rowText });
  await expect(row).toBeVisible(NAV);
  await row.getByRole("button", { name: "Approve" }).click();
  await expect(row).toHaveCount(0, NAV);
}

test("owner lists a warehouse, admin approves it, it appears in search", async ({
  page,
  browser,
}) => {
  test.setTimeout(300_000);
  const run = Date.now().toString(36);
  const ownerName = `Ghala Owner ${run}`;
  const title = `E2E warehouse ${run}`;

  // A separate browser context for the admin, with the project's mobile settings.
  const { baseURL, viewport, userAgent, deviceScaleFactor, isMobile, hasTouch } =
    test.info().project.use;
  const adminContext = await browser.newContext({
    baseURL,
    viewport,
    userAgent,
    deviceScaleFactor,
    isMobile,
    hasTouch,
  });
  const admin = await adminContext.newPage();
  await signIn(admin, ADMIN_PHONE);

  // Owner: sign up, fill the owner profile, submit for verification.
  await signIn(page, newPhone().local, "Neema Owner");
  await page.goto("/en/owner/onboarding");
  await page.getByLabel("Public name").fill(ownerName);
  await page.getByLabel("NIDA number").fill("19900101123450000123");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Not submitted")).toBeVisible(NAV);
  await page.getByRole("button", { name: "Submit for verification" }).click();
  await expect(page.getByText("Under review")).toBeVisible(NAV);

  await approveIn(admin, "/en/admin/verifications", ownerName);

  // Owner: a warehouse listing through the wizard.
  await page.goto("/en/owner/listings/new");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Category").selectOption({ label: "Storage & property › Warehouses" });
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/en\/owner\/listings\/[0-9a-f-]{36}\/edit/, NAV);

  await page.getByLabel("Title (English)").fill(title);
  await page.getByLabel("Description (English)").fill("Dry warehouse near the port road.");
  await expect(page.getByLabel("Seats")).toHaveCount(0); // warehouse fields only (US3-AS1)
  await page.getByLabel("Size (m²) *").fill("450");
  await page.getByRole("button", { name: "Save and continue" }).click();

  await expect(page.getByRole("heading", { name: "Location" })).toBeVisible();
  await page.getByLabel("Region").selectOption({ label: "Dar es Salaam" });
  const district = page.getByLabel("District");
  await expect(district.locator("option")).not.toHaveCount(1, NAV);
  await district.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Save and continue" }).click();

  await expect(page.getByRole("heading", { name: "Photos" })).toBeVisible();
  await page.getByTestId("photo-input").setInputFiles({
    name: "warehouse.png",
    mimeType: "image/png",
    buffer: PNG,
  });
  await expect(page.getByText("Cover")).toBeVisible(NAV);
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Price per month (TSh)").fill("1500000");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Rules" })).toBeVisible();
  await page.getByRole("button", { name: "Save and continue" }).click();

  await expect(page.getByText("Everything is in place")).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("In review").first()).toBeVisible(NAV);

  // Not in search before approval (US3-AS2); in search after.
  await page.goto("/en/search?category=warehouses");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible(NAV);
  await expect(page.getByText(title)).toHaveCount(0);

  await approveIn(admin, "/en/admin/listings", title);
  await page.reload();
  await expect(page.getByText(title)).toBeVisible(NAV);
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  await adminContext.close();
});
