"use client";

import { useEffect, useRef, type ReactNode } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  children: ReactNode;
};

/** Bottom sheet on phones, centred dialog on wider screens. Uses native <dialog>. */
export function Sheet({ open, onClose, title, closeLabel, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={onClose}
      aria-label={title}
      className="m-0 mt-auto max-h-[85vh] w-full max-w-none rounded-t-[var(--radius-shell)] bg-surface p-0 text-ink shadow-soft backdrop:bg-ink/40 backdrop:backdrop-blur-sm sm:m-auto sm:max-w-lg sm:rounded-[var(--radius-shell)]"
    >
      <div className="flex items-center justify-between px-5 pb-2 pt-5">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full bg-card px-3 py-1.5 text-sm font-medium text-ink hover:bg-brand-50"
        >
          {closeLabel}
        </button>
      </div>
      <div className="overflow-y-auto px-5 pb-5 pt-2">{children}</div>
    </dialog>
  );
}
