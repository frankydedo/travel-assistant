import { useId, type ReactNode } from "react";
import { cn } from "./cn";

interface Props {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom";
  align?: "start" | "center" | "end";
  className?: string;
}

const ALIGN = {
  start: "left-0",
  center: "left-1/2 -translate-x-1/2",
  end: "right-0",
};

/**
 * Tooltip solo CSS: compare con hover e con il focus da tastiera (il trigger è focusabile).
 * Il testo è collegato con aria-describedby, quindi è letto anche dagli screen reader.
 */
export function Tooltip({ content, children, side = "bottom", align = "start", className }: Props) {
  const id = useId();
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      <span tabIndex={0} aria-describedby={id} className="inline-flex rounded-full">
        {children}
      </span>
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-30 w-max max-w-64 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs leading-snug font-normal text-white opacity-0 shadow-lg transition-opacity duration-150",
          "group-focus-within/tt:opacity-100 group-hover/tt:opacity-100 dark:bg-zinc-100 dark:text-zinc-900",
          side === "bottom" ? "top-full mt-1.5" : "bottom-full mb-1.5",
          ALIGN[align],
        )}
      >
        {content}
      </span>
    </span>
  );
}
