import { defineConfig, devices } from "@playwright/test";

// Smoke tests run against the compose stack at the 360×640 mobile viewport (Principle VI).
export default defineConfig({
  testDir: "tests/e2e",
  // One worker: parallel cold compiles in `next dev` trigger full reloads that drop navigations.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    ...devices["Pixel 5"],
    viewport: { width: 360, height: 640 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "mobile-chrome", use: { browserName: "chromium" } }],
});
