import type { ReactNode } from "react";
import { Icon, type IconName } from "../icons";

type Props = {
  label: ReactNode;
  value: ReactNode;
  icon?: IconName;
  /** Small note beside the value, e.g. a unit or a delta. */
  note?: ReactNode;
  /** Mini chart (MiniBars / MiniDots) on the right. */
  chart?: ReactNode;
  className?: string;
};

/** Big number with an icon chip and an optional mini chart, as in the reference dashboard. */
export function StatCard({ label, value, icon, note, chart, className = "" }: Props) {
  return (
    <div className={`rounded-[var(--radius-card)] bg-card p-5 ${className}`}>
      <p className="text-sm font-medium text-ink">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {icon && (
            <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
              <Icon name={icon} className="size-5" />
            </span>
          )}
          <p className="truncate text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
          {note && <span className="self-end pb-1 text-xs text-muted">{note}</span>}
        </div>
        {chart}
      </div>
    </div>
  );
}
