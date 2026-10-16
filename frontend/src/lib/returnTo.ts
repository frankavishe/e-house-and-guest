/** Only same-site paths are allowed after sign-in; anything else goes to the home page. */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  return value;
}

/** Prefix a path with the locale unless it already has one. */
export function withLocale(path: string, locale: string): string {
  return /^\/(sw|en)(\/|$)/.test(path) ? path : `/${locale}${path === "/" ? "" : path}`;
}
