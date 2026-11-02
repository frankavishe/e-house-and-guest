import type { ReactNode } from "react";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-card text-muted",
  brand: "bg-brand-50 text-brand-700",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
