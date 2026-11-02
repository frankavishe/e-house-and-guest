import { Link } from "@/i18n/navigation";

/** Ring mark plus the app name; links home. */
export function Logo({ name, className = "" }: { name: string; className?: string }) {
  return (
    <Link href="/" className={`flex items-center gap-2.5 font-semibold text-ink ${className}`}>
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-hero"
      >
        <span className="size-3.5 rounded-full border-[3px] border-white" />
      </span>
      <span className="truncate text-lg tracking-tight">{name}</span>
    </Link>
  );
}
