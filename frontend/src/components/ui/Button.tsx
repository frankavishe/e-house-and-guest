import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/50",
  secondary: "border border-line bg-surface text-ink hover:bg-canvas disabled:text-muted",
  ghost: "text-brand-700 hover:bg-brand-50 disabled:text-muted",
  danger: "bg-danger text-white hover:bg-danger/90 disabled:bg-danger/50",
};

const sizes: Record<Size, string> = {
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-5 text-base",
};

export function buttonClasses(variant: Variant = "primary", size: Size = "md", full = false) {
  return [
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
    "disabled:cursor-not-allowed",
    variants[variant],
    sizes[size],
    full ? "w-full" : "",
  ].join(" ");
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  full?: boolean;
  loading?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  full = false,
  loading = false,
  className = "",
  disabled,
  children,
  type = "button",
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={`${buttonClasses(variant, size, full)} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden
          className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      )}
      {children}
    </button>
  );
}
