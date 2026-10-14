import { Check } from "lucide-react";
import type { Phase } from "../api/types";
import { PHASES, PHASE_LABELS } from "../lib/format";
import { cn } from "./ui/cn";

const HINTS: Record<Phase, string> = {
  COLLECTING_REQUIREMENTS: "L'assistente raccoglie budget, meta e date",
  PROPOSING: "Il planner propone le varianti",
  AWAITING_CONFIRMATION: "Serve il tuo clic di conferma",
  BOOKED: "Viaggio prenotato",
};

/** Fasi della state machine del backend: le transizioni le decide il codice, non l'LLM. */
export function PhaseStepper({ phase }: { phase: Phase }) {
  const current = PHASES.indexOf(phase);
  return (
    <ol aria-label="Fasi della conversazione">
      {PHASES.map((p, i) => {
        const done = i < current || (p === "BOOKED" && i === current);
        const isCurrent = i === current;
        const last = i === PHASES.length - 1;
        return (
          <li key={p} className="grid grid-cols-[1.5rem_1fr] gap-3" aria-current={isCurrent ? "step" : undefined}>
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full text-[11px] font-semibold transition-colors",
                  done && "bg-emerald-500 text-white",
                  isCurrent && !done && "bg-indigo-600 text-white ring-4 ring-indigo-500/20 dark:bg-indigo-500",
                  !done && !isCurrent && "border border-zinc-300 bg-white text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900",
                )}
              >
                {done ? <Check className="size-3.5" aria-hidden /> : i + 1}
              </span>
              {!last && (
                <span
                  aria-hidden
                  className={cn("my-1 w-px flex-1", i < current ? "bg-emerald-400" : "bg-zinc-200 dark:bg-zinc-800")}
                />
              )}
            </div>
            <div className={cn("min-w-0", !last && "pb-3")}>
              <div
                className={cn(
                  "text-sm",
                  isCurrent ? "font-semibold" : done ? "text-zinc-700 dark:text-zinc-300" : "text-zinc-400 dark:text-zinc-500",
                )}
              >
                {PHASE_LABELS[p]}
              </div>
              {isCurrent && <div className="text-xs text-zinc-500 dark:text-zinc-400">{HINTS[p]}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
