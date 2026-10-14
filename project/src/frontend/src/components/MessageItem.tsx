import type { ConversationDetail, Message } from "../api/types";
import { formatClock, formatDateTime } from "../lib/format";
import { AssistantAvatar, UserAvatar } from "./Avatar";
import { ConfirmBooking, type BookingAttempt } from "./ConfirmBooking";
import { ItineraryCard } from "./ItineraryCard";
import { MessageProvenanceBadge, messageProvenance, type Provenance } from "./Provenance";
import { cn } from "./ui/cn";

export type { BookingAttempt };

interface Props {
  message: Message;
  conversation: ConversationDetail;
  userName: string;
  selectingId: string | null;
  booking: Record<string, BookingAttempt>;
  onSelectItinerary: (itineraryId: string) => void;
  onConfirmBooking: (itineraryId: string) => void;
}

const ASSISTANT_BUBBLE: Record<Provenance | "none", string> = {
  // Accento AI: bordo sfumato violet/indigo e fondo appena tinto.
  ai: "border border-violet-200/80 bg-linear-to-br from-violet-50/80 via-white to-indigo-50/40 shadow-sm shadow-violet-500/5 dark:border-violet-400/40 dark:from-violet-500/15 dark:via-zinc-900 dark:to-indigo-500/10",
  rules: "border border-dashed border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900",
  system: "border border-sky-200 bg-sky-50/70 dark:border-sky-500/25 dark:bg-sky-500/5",
  none: "border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900",
};

function Timestamp({ iso, align }: { iso: string; align: "start" | "end" }) {
  return (
    <time
      dateTime={iso}
      title={formatDateTime(iso)}
      className={cn(
        "text-[11px] text-zinc-400 tabular-nums opacity-0 transition-opacity group-focus-within/msg:opacity-100 group-hover/msg:opacity-100 dark:text-zinc-500",
        align === "end" && "text-right",
      )}
    >
      {formatClock(iso)}
    </time>
  );
}

export function MessageItem({
  message,
  conversation,
  userName,
  selectingId,
  booking,
  onSelectItinerary,
  onConfirmBooking,
}: Props) {
  const byId = new Map(conversation.itineraries.map((it) => [it.id, it]));
  const itineraries = message.itinerary_ids
    .map((id) => byId.get(id))
    .filter((it): it is NonNullable<typeof it> => it !== undefined);
  const isAssistant = message.role === "assistant";
  const kind = messageProvenance(message);

  return (
    <div className="group/msg space-y-3">
      <div className={cn("flex gap-3", !isAssistant && "flex-row-reverse")}>
        {isAssistant ? <AssistantAvatar kind={kind} /> : <UserAvatar name={userName} />}
        <div className={cn("flex max-w-[min(85%,42rem)] min-w-0 flex-col gap-1.5", isAssistant ? "items-start" : "items-end")}>
          {isAssistant && (
            <div className="flex items-center gap-2">
              <MessageProvenanceBadge message={message} />
              <Timestamp iso={message.created_at} align="start" />
            </div>
          )}
          <div
            className={cn(
              "px-4 py-2.5 text-[15px] leading-relaxed",
              isAssistant
                ? cn("rounded-2xl rounded-tl-md text-zinc-800 dark:text-zinc-100", ASSISTANT_BUBBLE[kind ?? "none"])
                : "rounded-2xl rounded-tr-md bg-indigo-600 text-white shadow-sm shadow-indigo-600/20 dark:bg-indigo-500",
            )}
          >
            {/* Testo mostrato così com'è: nessun dato strutturato viene estratto dal testo dell'LLM. */}
            <div className="break-words whitespace-pre-wrap">{message.content}</div>
          </div>
          {!isAssistant && <Timestamp iso={message.created_at} align="end" />}
        </div>
      </div>

      {itineraries.length > 0 && (
        <div className="grid grid-cols-1 items-start gap-4 sm:pl-11 @2xl:grid-cols-2 @5xl:grid-cols-3">
          {itineraries.map((it) => (
            <ItineraryCard
              key={it.id}
              itinerary={it}
              canSelect={conversation.phase === "PROPOSING" && it.status === "proposed"}
              busy={selectingId !== null}
              selecting={selectingId === it.id}
              onSelect={() => onSelectItinerary(it.id)}
            />
          ))}
        </div>
      )}

      {message.ui?.type === "confirm_booking" && (
        <div className="sm:pl-11">
          <ConfirmBooking
            itineraryId={message.ui.itinerary_id}
            conversation={conversation}
            attempt={booking[message.ui.itinerary_id]}
            onConfirm={onConfirmBooking}
          />
        </div>
      )}
    </div>
  );
}
