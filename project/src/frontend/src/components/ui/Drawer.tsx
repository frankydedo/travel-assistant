import { useEffect, type ReactNode } from "react";
import { cn } from "./cn";

type Breakpoint = "lg" | "xl";

// Classi statiche (Tailwind non vede classi composte a runtime).
const INLINE: Record<Breakpoint, string> = {
  lg: "lg:visible lg:static lg:z-auto lg:translate-x-0 lg:shadow-none",
  xl: "xl:visible xl:static xl:z-auto xl:translate-x-0 xl:shadow-none",
};
const HIDE_BACKDROP: Record<Breakpoint, string> = { lg: "lg:hidden", xl: "xl:hidden" };

interface Props {
  side: "left" | "right";
  open: boolean;
  onClose: () => void;
  /** Da questa larghezza in su il pannello è sempre visibile, in linea con il layout. */
  inlineFrom: Breakpoint;
  label: string;
  className?: string;
  children: ReactNode;
}

/** Pannello laterale: fisso in linea sugli schermi larghi, drawer apribile su quelli stretti. */
export function Drawer({ side, open, onClose, inlineFrom, label, className, children }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {open && (
        <div
          aria-hidden
          onClick={onClose}
          className={cn("fixed inset-0 z-30 bg-zinc-950/40 backdrop-blur-[2px]", HIDE_BACKDROP[inlineFrom])}
        />
      )}
      <aside
        aria-label={label}
        className={cn(
          "fixed inset-y-0 z-40 flex w-[min(20rem,88vw)] flex-col shadow-2xl transition-[translate,visibility] duration-200",
          side === "left" ? "left-0" : "right-0",
          open ? "visible translate-x-0" : cn("invisible", side === "left" ? "-translate-x-full" : "translate-x-full"),
          INLINE[inlineFrom],
          className,
        )}
      >
        {children}
      </aside>
    </>
  );
}
