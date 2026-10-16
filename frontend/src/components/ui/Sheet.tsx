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
      className="m-0 mt-auto max-h-[85vh] w-full max-w-none rounded-t-2xl bg-surface p-0 text-ink backdrop:bg-black/40 sm:m-auto sm:max-w-lg sm:rounded-2xl"
    >
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-2 py-1 text-sm text-brand-700 hover:bg-brand-50"
        >
          {closeLabel}
        </button>
      </div>
      <div className="overflow-y-auto p-4">{children}</div>
    </dialog>
  );
}
