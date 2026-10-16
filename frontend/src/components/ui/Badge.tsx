import type { ReactNode } from "react";

type Tone = "neutral" | "brand" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-canvas text-muted border-line",
  brand: "bg-brand-50 text-brand-800 border-brand-100",
  warning: "bg-amber-50 text-amber-800 border-amber-200",
  danger: "bg-red-50 text-danger border-red-200",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
