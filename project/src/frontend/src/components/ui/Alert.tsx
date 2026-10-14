import type { ReactNode } from "react";
import { CircleCheck, TriangleAlert, X } from "lucide-react";
import { cn } from "./cn";

interface Props {
  tone?: "error" | "success";
  children: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

/** Messaggio inline in stile toast: errore o conferma. */
export function Alert({ tone = "error", children, onDismiss, className }: Props) {
  const isError = tone === "error";
  const Icon = isError ? TriangleAlert : CircleCheck;
  return (
    <div
      role={isError ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm shadow-sm",
        isError
          ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200"
          : "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200",
        className,
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Chiudi messaggio"
          className="-m-1 rounded-md p-1 opacity-70 hover:opacity-100"
        >
          <X className="size-4" aria-hidden />
        </button>
      )}
    </div>
  );
}
