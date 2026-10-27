"use client";

import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { Icon } from "@/components/icons";
import { Button } from "@/components/ui/Button";

/** Keeps the header and offers a retry when a page fails to render. */
export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  const t = useTranslations();
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div
      role="alert"
      className="mx-auto my-6 flex max-w-md flex-col items-center gap-4 rounded-[var(--radius-card)] bg-card px-6 py-12 text-center sm:my-12"
    >
      <span className="flex size-14 items-center justify-center rounded-full bg-danger-soft text-danger">
        <Icon name="alert" />
      </span>
      <p className="text-ink">{t("errors.generic")}</p>
      <Button onClick={reset}>{t("common.retry")}</Button>
    </div>
  );
}
