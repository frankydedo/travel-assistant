import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Compass, ListChecks, PanelLeft, Plus, Trash2 } from "lucide-react";
import {
  ApiError,
  createBooking,
  createConversation,
  deleteConversation,
  errorMessage,
  getConversation,
  listConversations,
  renameConversation,
  selectItinerary,
  sendMessageStream,
  StreamError,
  StreamInterruptedError,
} from "../api/client";
import type { ConversationDetail, ConversationSummary } from "../api/types";
import { UserAvatar } from "../components/Avatar";
import { Composer } from "../components/Composer";
import { ConversationSidebar } from "../components/ConversationSidebar";
import { MessageItem, type BookingAttempt } from "../components/MessageItem";
import { StatusPanel } from "../components/StatusPanel";
import { SuggestionChips } from "../components/SuggestionChips";
import { StreamingMessage, type StreamingState } from "../components/StreamingMessage";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Drawer } from "../components/ui/Drawer";
import { Skeleton } from "../components/ui/Skeleton";
import { PHASE_LABELS } from "../lib/format";
import { PHASE_TONE } from "../lib/styles";
import { uuid } from "../lib/uuid";

const byNewest = (a: ConversationSummary, b: ConversationSummary) =>
  (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at);

function toSummary(d: ConversationDetail): ConversationSummary {
  return { id: d.id, title: d.title, phase: d.phase, created_at: d.created_at, updated_at: d.updated_at };
}

export function ChatPage({ userName }: { userName: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("c");
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const conversationsRef = useRef(conversations);
  conversationsRef.current = conversations;
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState<ConversationSummary | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [draft, setDraft] = useState("");
  const [sendingFor, setSendingFor] = useState<string | null>(null);
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  // Risposta in arrivo via SSE per la conversazione in sendingFor.
  const [stream, setStream] = useState<StreamingState | null>(null);

  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [booking, setBooking] = useState<Record<string, BookingAttempt>>({});
  // Una Idempotency-Key per tentativo di conferma, riusata se si riprova dopo un errore di rete.
  const idempotencyKeys = useRef(new Map<string, string>());

  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Drawer per schermi stretti (su quelli larghi i pannelli sono sempre visibili).
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const closePanel = useCallback(() => setPanelOpen(false), []);

  const selectConversation = useCallback(
    (id: string, replace = false) => setSearchParams({ c: id }, { replace }),
    [setSearchParams],
  );

  const upsertSummary = useCallback((d: ConversationDetail) => {
    setConversations((prev) => [toSummary(d), ...prev.filter((c) => c.id !== d.id)].sort(byNewest));
  }, []);

  /** Sostituisce lo stato locale con quello restituito dal server (fonte di verità). */
  const applyDetail = useCallback(
    (d: ConversationDetail) => {
      upsertSummary(d);
      if (d.id === selectedIdRef.current) setDetail(d);
    },
    [upsertSummary],
  );

  const refreshList = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations([...list].sort(byNewest));
      setListError(null);
      return list;
    } catch (err) {
      setListError(errorMessage(err));
      return null;
    } finally {
      setListLoading(false);
    }
  }, []);

  const refreshDetail = useCallback(async (id: string) => {
    try {
      const d = await getConversation(id);
      if (d.id === selectedIdRef.current) {
        setDetail(d);
        setDetailError(null);
      }
    } catch (err) {
      if (id === selectedIdRef.current) setDetailError(errorMessage(err));
    }
  }, []);

  // Lista conversazioni all'avvio; se nessuna è selezionata apre la più recente.
  useEffect(() => {
    void refreshList().then((list) => {
      if (!selectedIdRef.current && list && list.length > 0) {
        const newest = [...list].sort(byNewest)[0];
        if (newest) selectConversation(newest.id, true);
      }
    });
  }, [refreshList, selectConversation]);

  // Carica il dettaglio quando cambia la conversazione selezionata.
  useEffect(() => {
    setChatError(null);
    setDetailError(null);
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setDetail((prev) => (prev?.id === selectedId ? prev : null));
    setLoadingDetail(true);
    void refreshDetail(selectedId).finally(() => setLoadingDetail(false));
  }, [selectedId, refreshDetail]);

  const streamText = stream?.text ?? "";
  const streamStatus = stream?.status ?? null;
  useEffect(() => {
    // Durante lo streaming del testo niente animazione: ogni token riavvierebbe lo scroll morbido.
    endRef.current?.scrollIntoView({ behavior: streamText ? "auto" : "smooth", block: "end" });
  }, [detail?.messages.length, pendingText, streamText, streamStatus]);

  // Su mobile, scegliere una conversazione chiude il drawer.
  useEffect(() => {
    setSidebarOpen(false);
  }, [selectedId]);

  async function handleCreate() {
    setCreating(true);
    setListError(null);
    try {
      const d = await createConversation();
      selectedIdRef.current = d.id;
      setDetail(d);
      upsertSummary(d);
      selectConversation(d.id);
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  /** Applica un titolo a lista e dettaglio (usato sia per l'ottimistico sia per il rollback). */
  const setTitle = useCallback((id: string, title: string | null) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
    setDetail((d) => (d && d.id === id ? { ...d, title } : d));
  }, []);

  async function handleRename(id: string, title: string) {
    const previous = conversations.find((c) => c.id === id)?.title ?? null;
    setTitle(id, title);
    try {
      const updated = await renameConversation(id, title);
      setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)).sort(byNewest));
      setDetail((d) => (d && d.id === id ? { ...d, ...updated } : d));
    } catch (err) {
      setTitle(id, previous);
      throw err;
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    setListError(null);
    try {
      await deleteConversation(id);
    } catch (err) {
      // 404: già eliminata altrove, la si toglie comunque dalla lista.
      if (!(err instanceof ApiError && err.status === 404)) {
        setListError(`Eliminazione non riuscita: ${errorMessage(err)}`);
        setDeletingId(null);
        return;
      }
    }
    // Lista letta dal ref: dopo l'await lo stato catturato dalla closure può essere vecchio.
    const remaining = conversationsRef.current.filter((c) => c.id !== id);
    setConversations(remaining);
    setDeletingId(null);
    if (id === selectedIdRef.current) {
      // Come all'avvio: si apre la più recente rimasta, altrimenti lo stato vuoto.
      const next = [...remaining].sort(byNewest)[0];
      setDetail(null);
      if (next) {
        selectedIdRef.current = next.id;
        selectConversation(next.id, true);
      } else {
        selectedIdRef.current = null;
        setSearchParams({}, { replace: true });
      }
    }
  }

  async function handleSend(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!detail || !text || sendingFor) return;
    const convId = detail.id;
    setSendingFor(convId);
    setPendingText(text);
    setDraft("");
    setChatError(null);
    const empty: StreamingState = { status: null, provider: null, text: "" };
    setStream(empty);
    try {
      const d = await sendMessageStream(convId, text, {
        onProgress: (p) => setStream((s) => s && { ...s, status: p.message }),
        onProvider: (info) => setStream((s) => s && { ...s, provider: info }),
        onToken: (t) => setStream((s) => s && { ...s, text: s.text + t }),
        // Il provider è caduto a metà e il backend è passato a un altro: si riparte da capo.
        onReset: () => setStream((s) => s && { ...s, provider: null, text: "" }),
        onFallback: () => setStream(empty),
      });
      applyDetail(d);
    } catch (err) {
      if (err instanceof StreamError || err instanceof StreamInterruptedError) {
        // Lo stream era partito: il server ha già il messaggio. Si mostra l'errore e si rilegge lo stato reale.
        if (convId === selectedIdRef.current) setChatError(errorMessage(err));
        await Promise.all([refreshDetail(convId), refreshList()]);
      } else if (convId === selectedIdRef.current) {
        // Errore prima dello stream (4xx, rete): il messaggio non è stato accettato, lo si rimette nel composer.
        setChatError(errorMessage(err));
        setDraft(text);
      }
    } finally {
      setSendingFor(null);
      setPendingText(null);
      setStream(null);
    }
  }

  async function handleSelectItinerary(itineraryId: string) {
    setSelectingId(itineraryId);
    setChatError(null);
    try {
      applyDetail(await selectItinerary(itineraryId));
    } catch (err) {
      setChatError(errorMessage(err));
    } finally {
      setSelectingId(null);
    }
  }

  async function handleConfirmBooking(itineraryId: string) {
    if (!detail) return;
    const convId = detail.id;
    let key = idempotencyKeys.current.get(itineraryId);
    if (!key) {
      key = uuid();
      idempotencyKeys.current.set(itineraryId, key);
    }
    setBooking((b) => ({ ...b, [itineraryId]: { busy: true, error: null } }));
    try {
      await createBooking(itineraryId, key);
      idempotencyKeys.current.delete(itineraryId);
      setBooking((b) => ({ ...b, [itineraryId]: { busy: false, error: null } }));
      await Promise.all([refreshDetail(convId), refreshList()]);
    } catch (err) {
      const definitive = err instanceof ApiError && err.status < 500;
      // Esito definitivo (4xx): il prossimo tentativo usa una chiave nuova.
      // Errore di rete o 5xx: esito ignoto, si conserva la chiave per un retry idempotente.
      if (definitive) idempotencyKeys.current.delete(itineraryId);
      const msg = definitive ? errorMessage(err) : `${errorMessage(err)}. Puoi riprovare in sicurezza.`;
      setBooking((b) => ({ ...b, [itineraryId]: { busy: false, error: msg } }));
      if (err instanceof ApiError && err.status === 409) {
        await Promise.all([refreshDetail(convId), refreshList()]);
      }
    }
  }

  const sending = sendingFor !== null && sendingFor === detail?.id;
  const onlyGreeting =
    detail !== null &&
    detail.phase === "COLLECTING_REQUIREMENTS" &&
    !detail.messages.some((m) => m.role === "user") &&
    !sending;

  function pickSuggestion(text: string) {
    setDraft(text);
    requestAnimationFrame(() => {
      const el = composerRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(text.length, text.length);
    });
  }

  return (
    <div className="flex h-full min-h-0">
      <Drawer
        side="left"
        open={sidebarOpen}
        onClose={closeSidebar}
        inlineFrom="lg"
        label="Conversazioni"
        className="border-r border-zinc-200 bg-zinc-50 lg:bg-zinc-100/60 dark:border-zinc-800 dark:bg-zinc-950 lg:dark:bg-zinc-900/40"
      >
        <ConversationSidebar
          conversations={conversations}
          loading={listLoading}
          selectedId={selectedId}
          onSelect={(id) => selectConversation(id)}
          onCreate={() => void handleCreate()}
          creating={creating}
          error={listError}
          onRename={handleRename}
          onDelete={(id) => setToDelete(conversations.find((c) => c.id === id) ?? null)}
          deletingId={deletingId}
          onClose={closeSidebar}
        />
      </Drawer>

      <ConfirmDialog
        open={toDelete !== null}
        tone="danger"
        icon={
          <span className="flex size-10 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300">
            <Trash2 className="size-5" aria-hidden />
          </span>
        }
        title="Eliminare la conversazione?"
        description="Messaggi e proposte verranno eliminati definitivamente. Le prenotazioni confermate restano nella pagina Prenotazioni."
        confirmLabel="Elimina"
        onConfirm={() => {
          const target = toDelete;
          setToDelete(null);
          if (target) void handleDelete(target.id);
        }}
        onCancel={() => setToDelete(null)}
      />

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-zinc-200 bg-white/70 px-3 backdrop-blur sm:px-4 dark:border-zinc-800 dark:bg-zinc-900/40">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Apri conversazioni"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            <PanelLeft className="size-4" aria-hidden />
          </Button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">
            {detail?.title || (selectedId ? "Nuova conversazione" : "Chat")}
          </h1>
          {detail && (
            <Badge tone={PHASE_TONE[detail.phase]} className="hidden sm:inline-flex">
              {PHASE_LABELS[detail.phase]}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="xl:hidden"
            aria-label="Apri stato della conversazione"
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen(true)}
          >
            <ListChecks className="size-4" aria-hidden />
          </Button>
        </header>

        <div className="@container min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl px-3 py-6 sm:px-6">
            {!selectedId && !listLoading && (
              <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center">
                <span className="flex size-14 items-center justify-center rounded-2xl bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
                  <Compass className="size-7" aria-hidden />
                </span>
                <h2 className="mt-5 text-xl font-semibold">Pianifica il tuo prossimo viaggio</h2>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                  Racconta budget, meta, mese e cosa ti piace fare. L'assistente raccoglie i requisiti, il sistema
                  calcola itinerari completi entro il budget e tu prenoti con un clic.
                </p>
                <Button
                  className="mt-6"
                  onClick={() => void handleCreate()}
                  loading={creating}
                  icon={<Plus className="size-4" aria-hidden />}
                >
                  Nuova conversazione
                </Button>
              </div>
            )}

            {((selectedId && !detail && loadingDetail) || (!selectedId && listLoading)) && (
              <div className="space-y-6" aria-label="Caricamento conversazione">
                {[0, 1, 2].map((i) => (
                  <div key={i} className={i % 2 ? "flex flex-row-reverse gap-3" : "flex gap-3"}>
                    <Skeleton className="size-8 rounded-full" />
                    <Skeleton className={i % 2 ? "h-12 w-1/3 rounded-2xl" : "h-20 w-1/2 rounded-2xl"} />
                  </div>
                ))}
              </div>
            )}

            {detailError && <Alert className="mb-4">{detailError}</Alert>}

            {detail && (
              <div className="space-y-6">
                {detail.messages.map((m) => (
                  <MessageItem
                    key={m.id}
                    message={m}
                    conversation={detail}
                    userName={userName}
                    selectingId={selectingId}
                    booking={booking}
                    onSelectItinerary={(id) => void handleSelectItinerary(id)}
                    onConfirmBooking={(id) => void handleConfirmBooking(id)}
                  />
                ))}
                {sending && pendingText && (
                  <div className="flex flex-row-reverse gap-3 opacity-70">
                    <UserAvatar name={userName} />
                    <div className="max-w-[min(85%,42rem)] rounded-2xl rounded-tr-md bg-indigo-600 px-4 py-2.5 text-[15px] leading-relaxed break-words whitespace-pre-wrap text-white dark:bg-indigo-500">
                      {pendingText}
                    </div>
                  </div>
                )}
                {sending && stream && <StreamingMessage stream={stream} />}
                <div ref={endRef} />
              </div>
            )}
          </div>
        </div>

        {detail && (
          <div className="shrink-0 border-t border-zinc-200 bg-zinc-50/90 px-3 py-3 backdrop-blur sm:px-6 dark:border-zinc-800 dark:bg-zinc-950/80">
            <div className="mx-auto max-w-4xl space-y-3">
              {onlyGreeting && <SuggestionChips onPick={pickSuggestion} />}
              {chatError && <Alert onDismiss={() => setChatError(null)}>{chatError}</Alert>}
              <Composer
                ref={composerRef}
                value={draft}
                onChange={setDraft}
                onSubmit={() => void handleSend()}
                disabled={sending}
              />
              <p className="hidden text-center text-[11px] text-zinc-400 sm:block dark:text-zinc-500">
                Invio per inviare · Maiusc+Invio per andare a capo · prezzi e disponibilità sono sempre calcolati dal
                sistema, mai dall'AI
              </p>
            </div>
          </div>
        )}
      </section>

      <Drawer
        side="right"
        open={panelOpen}
        onClose={closePanel}
        inlineFrom="xl"
        label="Stato della conversazione"
        className="border-l border-zinc-200 bg-zinc-50 xl:bg-zinc-100/60 dark:border-zinc-800 dark:bg-zinc-950 xl:dark:bg-zinc-900/40"
      >
        <StatusPanel conversation={detail} onClose={closePanel} />
      </Drawer>
    </div>
  );
}
