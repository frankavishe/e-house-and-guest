import type { ReactNode } from "react";
import { Icon, type IconName } from "../icons";

/** Dashed placeholder for an empty list: icon chip, a line of text and an optional action. */
export function EmptyState({
  icon = "inbox",
  action,
  children,
}: {
  icon?: IconName;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed border-line p-10 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-brand-100 text-brand-700">
        <Icon name={icon} />
      </span>
      <p className="text-muted">{children}</p>
      {action}
    </div>
  );
}
