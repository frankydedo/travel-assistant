import { MessageSquare, Plus, X } from "lucide-react";
import type { ConversationSummary } from "../api/types";
import { formatDateTime, formatRelative, PHASE_LABELS } from "../lib/format";
import { PHASE_TONE } from "../lib/styles";
import { Alert } from "./ui/Alert";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { cn } from "./ui/cn";
import { Skeleton } from "./ui/Skeleton";

interface Props {
  conversations: ConversationSummary[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating: boolean;
  error: string | null;
  /** Presente solo quando la sidebar è aperta come drawer. */
  onClose?: () => void;
}

export function ConversationSidebar({
  conversations,
  loading,
  selectedId,
  onSelect,
  onCreate,
  creating,
  error,
  onClose,
}: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 p-3">
        <Button
          className="flex-1"
          onClick={onCreate}
          loading={creating}
          icon={<Plus className="size-4" aria-hidden />}
        >
          {creating ? "Creazione…" : "Nuova conversazione"}
        </Button>
        {onClose && (
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Chiudi conversazioni" onClick={onClose}>
            <X className="size-4" aria-hidden />
          </Button>
        )}
      </div>

      <div className="px-4 pt-1 pb-2 text-[11px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
        Conversazioni
      </div>

      {error && (
        <div className="px-3 pb-2">
          <Alert>{error}</Alert>
        </div>
      )}

      <nav aria-label="Storico conversazioni" className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading && conversations.length === 0 ? (
          <ul className="space-y-1" aria-label="Caricamento conversazioni">
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="space-y-2 rounded-xl px-3 py-2.5">
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-3 w-1/2" />
              </li>
            ))}
          </ul>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => {
              const active = c.id === selectedId;
              const when = c.updated_at || c.created_at;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    onClick={() => onSelect(c.id)}
                    className={cn(
                      "flex w-full items-start gap-2.5 rounded-xl px-3 py-2.5 text-left transition-colors",
                      active
                        ? "bg-white shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-800 dark:ring-zinc-700"
                        : "hover:bg-zinc-200/50 dark:hover:bg-zinc-800/60",
                    )}
                  >
                    <MessageSquare
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        active ? "text-indigo-600 dark:text-indigo-400" : "text-zinc-400",
                      )}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{c.title || "Nuova conversazione"}</span>
                      <span className="mt-1 flex items-center gap-2">
                        <Badge tone={PHASE_TONE[c.phase]} className="text-[10px]">
                          {PHASE_LABELS[c.phase]}
                        </Badge>
                        <time
                          dateTime={when}
                          title={formatDateTime(when)}
                          className="truncate text-[11px] text-zinc-500 dark:text-zinc-400"
                        >
                          {formatRelative(when)}
                        </time>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
            {conversations.length === 0 && !error && (
              <li className="px-3 py-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
                Nessuna conversazione.
              </li>
            )}
          </ul>
        )}
      </nav>
    </div>
  );
}
