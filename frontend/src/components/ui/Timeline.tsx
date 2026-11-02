import type { ReactNode } from "react";

export type TimelineStep = {
  label: ReactNode;
  /** Time or note on the right. */
  meta?: ReactNode;
  state: "done" | "current" | "todo";
};

/** Vertical step list, like the Receipt → Preparation → Dispatch list in the reference. */
export function Timeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className="flex flex-col">
      {steps.map((step, i) => (
        <li key={i} className="relative flex items-center gap-3 py-1.5 text-sm">
          {i < steps.length - 1 && (
            <span
              aria-hidden
              className={`absolute left-[7px] top-[22px] h-[calc(100%-12px)] w-px ${
                step.state === "done" ? "bg-brand-400" : "bg-line"
              }`}
            />
          )}
          <span
            aria-hidden
            className={`relative z-[1] flex size-[15px] shrink-0 items-center justify-center rounded-full border-2 ${
              step.state === "todo"
                ? "border-line bg-surface"
                : step.state === "current"
                  ? "border-brand-600 bg-surface"
                  : "border-brand-500 bg-brand-500"
            }`}
          >
            {step.state === "current" && <span className="size-1.5 rounded-full bg-brand-600" />}
          </span>
          <span
            aria-current={step.state === "current" ? "step" : undefined}
            className={step.state === "todo" ? "text-muted" : "font-medium text-ink"}
          >
            {step.label}
          </span>
          {step.meta && <span className="ml-auto text-xs text-muted">{step.meta}</span>}
        </li>
      ))}
    </ol>
  );
}
