"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Icon } from "./icons";

type Theme = "light" | "dark";

export const THEME_KEY = "theme";
const THEME_EVENT = "themechange";

/** Runs before paint (inline in <head>) so the stored or OS theme applies without a flash. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}})()`;

/** Current theme plus a setter that applies, remembers and broadcasts it to other toggles. */
function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const sync = () =>
      setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    sync();
    window.addEventListener(THEME_EVENT, sync);
    return () => window.removeEventListener(THEME_EVENT, sync);
  }, []);

  function choose(next: Theme) {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // private mode: the choice lasts for this page only
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  }

  return [theme, choose];
}

/** Light/Dark segmented switch; the choice is remembered on this device. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const t = useTranslations("theme");
  const [theme, choose] = useTheme();

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
            theme === option ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
          }`}
        >
          {t(option)}
        </button>
      ))}
    </div>
  );
}

/** Compact sun/moon button for the header; shows the theme it switches to. */
export function ThemeIconButton({ className = "" }: { className?: string }) {
  const t = useTranslations("theme");
  const [theme, choose] = useTheme();
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => choose(next)}
      aria-label={`${t("label")}: ${t(next)}`}
      title={t(next)}
      className={className}
    >
      {/* CSS picks the icon so it is right before hydration too. */}
      <Icon name="moon" className="size-5 dark:hidden" />
      <Icon name="sun" className="hidden size-5 dark:block" />
    </button>
  );
}
