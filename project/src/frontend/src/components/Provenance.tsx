// Marcatori di provenienza: rendono visibile il principio
// "l'LLM capisce e spiega, il codice decide e garantisce".
//   ai     -> testo generato da un modello (GEMINI/GROQ/LMSTUDIO): icona Sparkles, accento violet
//   rules  -> provider di riserva deterministico (MOCK): icona Cpu, neutro
//   system -> messaggio o dato prodotto dal codice (SYSTEM, prezzi, itinerari): icona ShieldCheck/Calculator
import { Calculator, Cpu, ShieldCheck, Sparkles } from "lucide-react";
import type { Message } from "../api/types";
import { Tooltip } from "./ui/Tooltip";
import { cn } from "./ui/cn";

export type Provenance = "ai" | "rules" | "system";

/** Campi di provenienza di un messaggio (anche di uno ancora in streaming). */
export type ProvenanceSource = Pick<Message, "role" | "provider" | "model" | "ai_generated">;

export function messageProvenance(m: ProvenanceSource): Provenance | null {
  if (m.role !== "assistant") return null;
  if (m.ai_generated) return "ai";
  if (m.provider === "MOCK") return "rules";
  if (m.provider === "SYSTEM") return "system";
  return null;
}

const PILL = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset";

/** Etichetta sopra il testo di un messaggio dell'assistente. */
export function MessageProvenanceBadge({ message }: { message: ProvenanceSource }) {
  const kind = messageProvenance(message);
  if (kind === "ai") {
    const provider = message.provider ?? "LLM";
    return (
      <Tooltip
        content={
          <>
            Testo generato da un modello linguistico ({provider})
            {message.model ? <> · modello: {message.model}</> : null}. Prezzi e disponibilità non vengono dal modello.
          </>
        }
      >
        <span
          className={cn(
            PILL,
            "bg-linear-to-r from-violet-50 to-indigo-50 text-violet-700 ring-violet-200 dark:from-violet-500/15 dark:to-indigo-500/15 dark:text-violet-200 dark:ring-violet-400/30",
          )}
        >
          <Sparkles className="size-3" aria-hidden />
          Generato con AI · {provider}
        </span>
      </Tooltip>
    );
  }
  if (kind === "rules") {
    return (
      <Tooltip content={<>Generata dal provider di riserva deterministico (regole, non AI){message.model ? <> · {message.model}</> : null}</>}>
        <span className={cn(PILL, "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700")}>
          <Cpu className="size-3" aria-hidden />
          Risposta di riserva
        </span>
      </Tooltip>
    );
  }
  if (kind === "system") {
    return (
      <Tooltip content="Messaggio prodotto direttamente dal codice dell'applicazione, senza modello linguistico">
        <span className={cn(PILL, "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-200 dark:ring-sky-500/30")}>
          <ShieldCheck className="size-3" aria-hidden />
          Messaggio di sistema
        </span>
      </Tooltip>
    );
  }
  return null;
}

/** Piccola icona Sparkles accanto a un contenuto generato con AI. */
export function AiMarker({ label, className }: { label: string; className?: string }) {
  return (
    <Tooltip content={label} className={className}>
      <span className="inline-flex size-4 items-center justify-center rounded-full text-violet-500 dark:text-violet-300">
        <Sparkles className="size-3.5" aria-hidden />
        <span className="sr-only">{label}</span>
      </span>
    </Tooltip>
  );
}

/** Marcatore "Calcolato dal sistema" per prezzi e dati prodotti dal codice. */
export function ComputedMarker({
  label = "Calcolato dal sistema",
  align = "start",
}: {
  label?: string;
  align?: "start" | "center" | "end";
}) {
  return (
    <Tooltip
      align={align}
      content="Prezzi, disponibilità e ID sono calcolati dal planner e verificati dal validatore deterministico: il modello non li può inventare né modificare."
    >
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
        <Calculator className="size-3" aria-hidden />
        {label}
      </span>
    </Tooltip>
  );
}

/** Legenda persistente dei marcatori di provenienza. */
export function ProvenanceLegend({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-zinc-200 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-zinc-900/60", className)}>
      <p className="mb-2 text-[11px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
        Chi ha prodotto cosa
      </p>
      <ul className="space-y-1.5 text-xs text-zinc-600 dark:text-zinc-300">
        <li className="flex items-center gap-2">
          <span className="flex w-8 shrink-0 items-center">
            <Sparkles className="size-3.5 text-violet-500 dark:text-violet-300" aria-hidden />
          </span>
          generato da AI
        </li>
        <li className="flex items-center gap-2">
          <span className="flex w-8 shrink-0 items-center">
            <Cpu className="size-3.5 text-zinc-500 dark:text-zinc-400" aria-hidden />
          </span>
          regole deterministiche
        </li>
        <li className="flex items-center gap-2">
          <span className="flex w-8 shrink-0 items-center gap-0.5">
            <ShieldCheck className="size-3.5 text-sky-600 dark:text-sky-300" aria-hidden />
            <Calculator className="size-3.5 text-zinc-500 dark:text-zinc-400" aria-hidden />
          </span>
          sistema / calcolato dal codice
        </li>
      </ul>
    </div>
  );
}
