/** Placeholder block that keeps layout stable while content loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-line ${className}`} />;
}
