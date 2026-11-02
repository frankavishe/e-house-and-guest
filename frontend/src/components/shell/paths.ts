/** Routes drawn inside the dashboard shell (sidebar, no public header). `pathname` has no locale. */
export function isDashboardPath(pathname: string) {
  if (pathname.startsWith("/account/sign-in")) return false;
  return /^\/(account|owner|admin)(\/|$)/.test(pathname);
}

/** Whether a nav item `href` is the current page. `exact` items only match themselves. */
export function isCurrent(pathname: string, href: string, exact = false) {
  return pathname === href || (!exact && pathname.startsWith(`${href}/`));
}
