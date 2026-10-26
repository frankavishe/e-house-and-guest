"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export const THEME_KEY = "theme";

/** Runs before paint (inline in <head>) so the stored or OS theme applies without a flash. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}})()`;

/** Light/Dark segmented switch; the choice is remembered on this device. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const t = useTranslations("theme");
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function choose(next: Theme) {
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // private mode: the choice lasts for this page only
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label={t("label")}
      className={`grid grid-cols-2 gap-1 rounded-full bg-card p-1 text-sm font-medium ${className}`}
    >
      {(["light", "dark"] as const).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={theme === option}
          onClick={() => choose(option)}
          className={`rounded-full px-3 py-1.5 transition-colors ${
            theme === option ? "bg-ink text-surface" : "text-muted hover:text-ink"
          }`}
        >
          {t(option)}
        </button>
      ))}
    </div>
  );
}
