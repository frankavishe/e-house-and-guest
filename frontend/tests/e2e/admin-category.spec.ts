// US7 smoke (quickstart V16): an admin adds a "Generators" rental type with power (kVA) and
// fuel fields; a verified owner lists one straight away, and once approved renters filter
// it by kVA. No code or deploy involved. 360×640.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { NAV, signIn } from "./helpers";

const ADMIN_PHONE = "0700000009"; // seeded admin (backend/seed/demo.yaml)
const OWNER_PHONE = "0700000003"; // seeded verified business owner

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

async function addField(
  admin: Page,
  n: number,
  field: { key: string; type: string; sw: string; en: string; filter: string },
): Promise<Locator> {
  await admin.getByRole("button", { name: "Add field" }).click();
  const box = admin.getByRole("group", { name: `Field ${n}` });
  await box.getByLabel("Key").fill(field.key);
  await box.getByLabel("Type").selectOption(field.type);
  await box.getByLabel("Label (Swahili)").first().fill(field.sw);
  await box.getByLabel("Label (English)").first().fill(field.en);
  await box.getByLabel("Search filter").selectOption(field.filter);
  return box;
}

test("admin adds Generators, an owner lists one, renters filter by kVA", async ({
  page,
  browser,
}) => {
  test.setTimeout(300_000);
  const run = Date.now().toString(36);
  const slug = `generators-${run}`;
  const name = `Generators ${run}`;
  const title = `E2E generator ${run}`;

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

  // Admin: the new rental type under "Equipment & supplies".
  await admin.goto("/en/admin/categories/new");
  await admin.waitForLoadState("networkidle");
  await admin.getByLabel("Slug").fill(slug);
  await admin.getByLabel("Name (Swahili)").fill(`Jenereta ${run}`);
  await admin.getByLabel("Name (English)").fill(name);
  const parent = admin.getByLabel("Parent group");
  const equipment = parent.locator("option", { hasText: "Equipment & supplies" }).first();
  await parent.selectOption((await equipment.getAttribute("value")) ?? "");
  await admin.getByLabel("Booking type").selectOption("QUANTITY");
  await admin.getByLabel("night", { exact: true }).uncheck();
  await admin.getByLabel("item per day").check();

  const power = await addField(admin, 1, {
    key: "power_kva",
    type: "decimal",
    sw: "Nguvu",
    en: "Power",
    filter: "range",
  });
  await power.getByLabel("Unit (Swahili)").fill("kVA");
  await power.getByLabel("Unit (English)").fill("kVA");
  await power.getByLabel("Required").check();
  const fuel = await addField(admin, 2, {
    key: "fuel",
    type: "enum",
    sw: "Mafuta",
    en: "Fuel",
    filter: "exact",
  });
  for (const [value, sw, en] of [
    ["diesel", "Dizeli", "Diesel"],
    ["petrol", "Petroli", "Petrol"],
  ]) {
    await fuel.getByRole("button", { name: "Add option" }).click();
    await fuel.getByLabel("Value").last().fill(value);
    await fuel.getByLabel("Label (Swahili)").last().fill(sw);
    await fuel.getByLabel("Label (English)").last().fill(en);
  }
  // The preview renders the owner form from the schema being edited.
  await expect(admin.getByText("Preview: owner form")).toBeVisible();
  await expect(admin.getByLabel("Power (kVA) *")).toBeVisible();

  await admin.getByRole("button", { name: "Create category" }).click();
  // `next dev` compiles the editor route on first use; give that navigation longer.
  await expect(admin).toHaveURL(/\/en\/admin\/categories\/[0-9a-f-]{36}$/, { timeout: 120_000 });
  await expect(admin.getByText("schema version 1")).toBeVisible(NAV);

  // Owner: a generator listing through the wizard; the fields come from the new schema.
  await signIn(page, OWNER_PHONE);
  await page.goto("/en/owner/listings/new");
  await page.waitForLoadState("networkidle");
  const category = page.getByLabel("Category");
  const option = category.locator("option", { hasText: name });
  await category.selectOption((await option.getAttribute("value")) ?? "");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/en\/owner\/listings\/[0-9a-f-]{36}\/edit/, NAV);

  await page.getByLabel("Title (English)").fill(title);
  await page.getByLabel("Description (English)").fill("Silent diesel generator for events.");
  await page.getByLabel("Power (kVA) *").fill("60");
  await page.getByLabel("Fuel").selectOption("diesel");
  await page.getByRole("button", { name: "Save and continue" }).click();

  await expect(page.getByRole("heading", { name: "Location" })).toBeVisible(NAV);
  await page.getByLabel("Region").selectOption({ label: "Dar es Salaam" });
  const district = page.getByLabel("District");
  await expect(district.locator("option")).not.toHaveCount(1, NAV);
  await district.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Save and continue" }).click();

  await expect(page.getByRole("heading", { name: "Photos" })).toBeVisible(NAV);
  await page.getByTestId("photo-input").setInputFiles({
    name: "generator.png",
    mimeType: "image/png",
    buffer: PNG,
  });
  await expect(page.getByText("Cover")).toBeVisible(NAV);
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Price per item per day (TSh)").fill("80000");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Rules" })).toBeVisible(NAV);
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByText("Everything is in place")).toBeVisible(NAV);
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("In review").first()).toBeVisible(NAV);

  // Admin approves the listing.
  await admin.goto("/en/admin/listings");
  await admin.waitForLoadState("networkidle");
  const row = admin.getByRole("listitem").filter({ hasText: title });
  await expect(row).toBeVisible(NAV);
  await row.getByRole("button", { name: "Approve" }).click();
  await expect(row).toHaveCount(0, NAV);

  // Renter (signed out): the kVA range filter is offered and works.
  const renter = await browser.newContext({ baseURL, viewport, isMobile });
  const visitor = await renter.newPage();
  await visitor.goto(`/en/search?category=${slug}`);
  await visitor.getByRole("button", { name: "Filters" }).click();
  await expect(
    visitor.getByRole("dialog", { name: "Filters" }).getByText("Power (kVA)"),
  ).toBeVisible();
  await visitor.goto(`/en/search?category=${slug}&attr.power_kva.min=50`);
  await expect(visitor.getByText(title)).toBeVisible(NAV);
  await visitor.goto(`/en/search?category=${slug}&attr.power_kva.min=100`);
  await expect(visitor.getByRole("heading", { level: 1 })).toBeVisible(NAV);
  await expect(visitor.getByText(title)).toHaveCount(0);

  await renter.close();
  await adminContext.close();
});
