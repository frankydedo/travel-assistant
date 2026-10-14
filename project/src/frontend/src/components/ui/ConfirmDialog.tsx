import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./Button";

interface Props {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  icon?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Dialog modale basato su <dialog>: focus trap, Esc e backdrop nativi. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Indietro",
  tone = "primary",
  icon,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onCancel();
      }}
      aria-labelledby="confirm-dialog-title"
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-2xl border border-zinc-200 bg-white p-0 text-zinc-900 shadow-2xl backdrop:bg-zinc-950/50 backdrop:backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
    >
      <div className="flex gap-4 p-6">
        {icon && <div className="shrink-0">{icon}</div>}
        <div className="min-w-0">
          <h2 id="confirm-dialog-title" className="text-base font-semibold">
            {title}
          </h2>
          <div className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">{description}</div>
        </div>
      </div>
      <div className="flex flex-col-reverse gap-2 border-t border-zinc-100 bg-zinc-50 px-6 py-4 sm:flex-row sm:justify-end dark:border-zinc-800 dark:bg-zinc-950/40">
        <Button variant="secondary" onClick={onCancel} autoFocus>
          {cancelLabel}
        </Button>
        <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
