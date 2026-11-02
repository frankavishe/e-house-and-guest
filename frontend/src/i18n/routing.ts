import { defineRouting } from "next-intl/routing";

// Swahili is the default language (FR-004); every page lives under /sw or /en.
export const routing = defineRouting({
  locales: ["sw", "en"],
  defaultLocale: "sw",
  localePrefix: "always",
});

export type AppLocale = (typeof routing.locales)[number];
