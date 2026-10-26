/** Ring showing `value` out of 100, with an optional label inside. */
export function ProgressRing({
  value,
  size = 44,
  label,
}: {
  value: number;
  size?: number;
  label?: string;
}) {
  const r = 16;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span
      className="relative inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg aria-hidden viewBox="0 0 40 40" className="size-full -rotate-90">
        <circle cx="20" cy="20" r={r} fill="none" strokeWidth="5" className="stroke-brand-100" />
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (pct / 100) * c}
          className="stroke-brand-600"
        />
      </svg>
      {label && <span className="absolute text-[10px] font-semibold">{label}</span>}
    </span>
  );
}
