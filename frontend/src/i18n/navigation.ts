import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

// Locale-aware Link/redirect/router: hrefs are written without the locale prefix.
export const { Link, redirect, usePathname, useRouter, getPathname } = createNavigation(routing);
