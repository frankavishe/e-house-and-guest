import type { ReactNode } from "react";

type Props = {
  title?: ReactNode;
  subtitle?: ReactNode;
  /** Right side of the title row, e.g. a "View more ›" link. */
  action?: ReactNode;
  /** `soft` is the grey tile inside the white shell; `surface` stands on the canvas. */
  tone?: "soft" | "surface" | "brand";
  as?: "section" | "div" | "article" | "aside";
  className?: string;
  children?: ReactNode;
};

const tones = {
  soft: "bg-card",
  surface: "bg-surface shadow-soft",
  brand: "bg-gradient-to-br from-brand-400 to-brand-700 text-white",
};

/** Rounded bento tile with an optional title row. */
export function Card({
  title,
  subtitle,
  action,
  tone = "soft",
  as: Tag = "section",
  className = "",
  children,
}: Props) {
  return (
    <Tag className={`rounded-[var(--radius-card)] p-5 ${tones[tone]} ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-lg font-semibold leading-tight">{title}</h2>}
            {subtitle && (
              <p className={`mt-0.5 text-xs ${tone === "brand" ? "text-white/80" : "text-muted"}`}>
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="shrink-0 text-sm">{action}</div>}
        </div>
      )}
      {children}
    </Tag>
  );
}
