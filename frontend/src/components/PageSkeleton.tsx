import { Skeleton } from "./ui/Skeleton";

/** Placeholder shown by the route `loading.tsx` files the moment a link is clicked, while the
 * next page renders on the server. */
export function PageSkeleton() {
  return (
    <div role="status" aria-busy="true" className="flex flex-col gap-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
