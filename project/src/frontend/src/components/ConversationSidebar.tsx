import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { MessageSquare, Pencil, Plus, Trash2, X } from "lucide-react";
import { errorMessage } from "../api/client";
import type { ConversationSummary } from "../api/types";
import { formatDateTime, formatRelative, PHASE_LABELS } from "../lib/format";
import { PHASE_TONE } from "../lib/styles";
import { Alert } from "./ui/Alert";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { cn } from "./ui/cn";
import { Skeleton } from "./ui/Skeleton";

export const TITLE_MAX_LENGTH = 80;

const DEFAULT_TITLE = "Nuova conversazione";

// Azioni sempre visibili su touch e schermi stretti; con mouse su schermo largo compaiono a hover/focus.
// Classi statiche: Tailwind non vede quelle composte a runtime.
const ACTIONS_VISIBILITY =
  "[@media(hover:hover)_and_(min-width:64rem)]:opacity-0 " +
  "[@media(hover:hover)_and_(min-width:64rem)]:group-hover:opacity-100 " +
  "[@media(hover:hover)_and_(min-width:64rem)]:group-focus-within:opacity-100";

interface Props {
  conversations: ConversationSummary[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating: boolean;
  error: string | null;
  /** Rinomina con aggiornamento ottimistico; rifiuta (dopo il rollback) se il server non accetta. */
  onRename: (id: string, title: string) => Promise<void>;
  /** Chiede conferma ed elimina la conversazione. */
  onDelete: (id: string) => void;
  /** Conversazione in corso di eliminazione (azioni disabilitate). */
  deletingId: string | null;
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
  onRename,
  onDelete,
  deletingId,
  onClose,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<{ id: string; message: string } | null>(null);

  function submitRename(c: ConversationSummary, value: string) {
    setEditingId(null);
    const title = value.trim();
    // Vuoto o invariato: equivale ad annullare.
    if (!title || title === (c.title ?? "")) return;
    setRenameError(null);
    onRename(c.id, title).catch((err: unknown) => {
      setRenameError({ id: c.id, message: `Rinomina non riuscita: ${errorMessage(err)}` });
    });
  }

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
                <li key={c.id} className={cn("group relative", deletingId === c.id && "pointer-events-none opacity-50")}>
                  {editingId === c.id ? (
                    <RenameField
                      initial={c.title ?? ""}
                      onSubmit={(value) => submitRename(c, value)}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <>
                      <button
                        type="button"
                        aria-current={active ? "true" : undefined}
                        onClick={() => onSelect(c.id)}
                        className={cn(
                          "flex w-full items-start gap-2.5 rounded-xl py-2.5 pr-17 pl-3 text-left transition-colors",
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
                          <span className="block truncate text-sm font-medium">{c.title || DEFAULT_TITLE}</span>
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
                      <div
                        className={cn(
                          "absolute top-1.5 right-1.5 flex items-center gap-0.5 transition-opacity",
                          ACTIONS_VISIBILITY,
                        )}
                      >
                        <ItemAction
                          label="Rinomina conversazione"
                          onClick={() => {
                            setRenameError(null);
                            setEditingId(c.id);
                          }}
                          disabled={deletingId === c.id}
                        >
                          <Pencil className="size-3.5" aria-hidden />
                        </ItemAction>
                        <ItemAction
                          label="Elimina conversazione"
                          danger
                          onClick={() => onDelete(c.id)}
                          disabled={deletingId === c.id}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </ItemAction>
                      </div>
                    </>
                  )}
                  {renameError?.id === c.id && (
                    <p role="alert" className="px-3 pt-1 pb-1.5 text-[11px] text-rose-600 dark:text-rose-300">
                      {renameError.message}
                    </p>
                  )}
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

function ItemAction({
  label,
  danger = false,
  disabled,
  onClick,
  children,
}: {
  label: string;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex size-7 items-center justify-center rounded-lg text-zinc-400 transition-colors disabled:opacity-50",
        danger
          ? "hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/10 dark:hover:text-rose-300"
          : "hover:bg-zinc-200/70 hover:text-zinc-700 dark:hover:bg-zinc-700/60 dark:hover:text-zinc-200",
      )}
    >
      {children}
    </button>
  );
}

/** Modifica in linea del titolo: Invio o blur salvano, Esc annulla. */
function RenameField({
  initial,
  onSubmit,
  onCancel,
}: {
  initial: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const inputRef = useRef<HTMLInputElement>(null);
  // Evita il doppio invio (Invio seguito dal blur dovuto allo smontaggio).
  const settled = useRef(false);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, []);

  function finish(save: boolean) {
    if (settled.current) return;
    settled.current = true;
    if (save) onSubmit(value);
    else onCancel();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      // Non deve chiudere anche il drawer.
      e.stopPropagation();
      finish(false);
    }
  }

  return (
    <div className="flex items-center gap-2.5 rounded-xl bg-white px-3 py-2.5 shadow-sm ring-2 ring-indigo-500/60 dark:bg-zinc-800">
      <MessageSquare className="size-4 shrink-0 text-indigo-600 dark:text-indigo-400" aria-hidden />
      <input
        ref={inputRef}
        type="text"
        value={value}
        maxLength={TITLE_MAX_LENGTH}
        aria-label="Titolo della conversazione"
        placeholder={DEFAULT_TITLE}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => finish(true)}
        className="min-w-0 flex-1 bg-transparent text-sm font-medium outline-none placeholder:text-zinc-400"
      />
    </div>
  );
}
