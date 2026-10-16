import { formatTZS } from "@/lib/format";

/** Integer TZS amount, e.g. `TSh 1,250,000`. */
export function Money({ amount, className = "" }: { amount: number; className?: string }) {
  return <span className={`tabular-nums ${className}`}>{formatTZS(amount)}</span>;
}
