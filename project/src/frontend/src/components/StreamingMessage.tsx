import { Markdown } from "./Markdown";
import type { StreamProviderInfo } from "../api/types";
import { AssistantAvatar } from "./Avatar";
import { ASSISTANT_BUBBLE } from "./MessageItem";
import { MessageProvenanceBadge, messageProvenance, type ProvenanceSource } from "./Provenance";
import { cn } from "./ui/cn";

export interface StreamingState {
  /** Ultimo messaggio di avanzamento (evento `progress`). */
  status: string | null;
  /** Chi sta generando la risposta (evento `provider`); null finché non inizia lo streaming del testo. */
  provider: StreamProviderInfo | null;
  /** Testo ricevuto finora (eventi `token`). */
  text: string;
}

const DEFAULT_STATUS = "L'assistente sta elaborando la richiesta…";

function Dots() {
  return (
    <span className="flex items-center gap-1" aria-hidden>
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-typing rounded-full bg-zinc-400 dark:bg-zinc-500"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

/** Bolla dell'assistente durante lo streaming: stato di avanzamento, poi il testo man mano che arriva. */
export function StreamingMessage({ stream }: { stream: StreamingState }) {
  const source: ProvenanceSource | null = stream.provider ? { role: "assistant", ...stream.provider } : null;
  const kind = source ? messageProvenance(source) : null;
  const status = stream.status ?? DEFAULT_STATUS;

  return (
    <div className="flex gap-3">
      <AssistantAvatar kind={kind} />
      <div className="flex max-w-[min(85%,42rem)] min-w-0 flex-col items-start gap-1.5">
        {source && kind && <MessageProvenanceBadge message={source} />}
        <div
          aria-busy="true"
          className={cn(
            "rounded-2xl rounded-tl-md px-4 py-2.5 text-[15px] leading-relaxed text-zinc-800 dark:text-zinc-100",
            ASSISTANT_BUBBLE[kind ?? "none"],
          )}
        >
          {stream.text ? (
            // Markdown come nei messaggi definitivi (anche parziale): nessun dato strutturato viene estratto da qui.
            <div>
              <Markdown text={stream.text} />
              <span
                aria-hidden
                className="ml-0.5 inline-block h-[1.1em] w-0.5 translate-y-[0.2em] rounded-full bg-current opacity-60 motion-safe:animate-caret"
              />
            </div>
          ) : (
            <div className="flex items-center gap-2.5 py-1 text-sm text-zinc-600 dark:text-zinc-400">
              <Dots />
              <span>{status}</span>
            </div>
          )}
        </div>
        <span className="sr-only" role="status" aria-live="polite">
          {stream.text ? "L'assistente sta scrivendo…" : status}
        </span>
      </div>
    </div>
  );
}
