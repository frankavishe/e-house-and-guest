"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";
import { Skeleton } from "./ui/Skeleton";

// Leaflet touches `window`, so the map renders on the client only, in its own chunk.
const SearchMap = dynamic(() => import("./SearchMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-[60vh] w-full rounded-[var(--radius-card)] lg:h-[calc(100dvh-8rem)]" />,
});

export function SearchMapLoader(props: ComponentProps<typeof SearchMap>) {
  return <SearchMap {...props} />;
}
