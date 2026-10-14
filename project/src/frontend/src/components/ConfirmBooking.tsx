import { ArrowRight, CircleCheck, Lock, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import type { ConversationDetail } from "../api/types";
import { formatEUR, VARIANT_LABELS } from "../lib/format";
import { ComputedMarker } from "./Provenance";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";

export interface BookingAttempt {
  busy: boolean;
  error: string | null;
}

interface Props {
  itineraryId: string;
  conversation: ConversationDetail;
  attempt: BookingAttempt | undefined;
  onConfirm: (itineraryId: string) => void;
}

/** Callout di conferma: l'unico punto da cui parte una prenotazione (human in the loop). */
export function ConfirmBooking({ itineraryId, conversation, attempt, onConfirm }: Props) {
  const it = conversation.itineraries.find((x) => x.id === itineraryId);
  const busy = attempt?.busy ?? false;
  const enabled = conversation.phase === "AWAITING_CONFIRMATION" && it?.status === "selected" && !busy;
  const booked = it?.status === "booked";

  return (
    <div className="rounded-2xl border border-indigo-200 bg-linear-to-br from-indigo-50 via-white to-white p-4 shadow-sm sm:p-5 dark:border-indigo-500/30 dark:from-indigo-500/10 dark:via-zinc-900 dark:to-zinc-900">
      <div className="flex items-start gap-3">
        <span
          className={
            booked
              ? "flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white"
              : "flex size-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/30"
          }
          aria-hidden
        >
          {booked ? <CircleCheck className="size-5" /> : <Lock className="size-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="font-semibold">{booked ? "Prenotazione confermata" : "Conferma la prenotazione"}</h4>
          {it && (
            <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-300">
              Variante {VARIANT_LABELS[it.variant]} · {it.destination}, {it.country_name} ·{" "}
              <strong className="font-semibold text-zinc-900 tabular-nums dark:text-zinc-50">
                {formatEUR(it.total_price)}
              </strong>
            </p>
          )}
          <div className="mt-1">
            <ComputedMarker label="Prezzo bloccato dal sistema" />
          </div>
        </div>
      </div>

      {booked ? (
        <Alert tone="success" className="mt-4">
          Tutto fatto: voli, hotel e attività sono prenotati.{" "}
          <Link
            to="/prenotazioni"
            className="inline-flex items-center gap-1 font-semibold underline underline-offset-2"
          >
            Vai alle prenotazioni <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </Alert>
      ) : (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <Button
            size="lg"
            className="w-full sm:w-auto"
            disabled={!enabled}
            loading={busy}
            icon={<Lock className="size-4" aria-hidden />}
            onClick={() => onConfirm(itineraryId)}
          >
            {busy ? "Prenotazione in corso…" : "Conferma e prenota"}
          </Button>
          <p className="inline-flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
            <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
            La prenotazione parte solo con questo clic.
          </p>
        </div>
      )}
      {attempt?.error && (
        <Alert className="mt-3">{attempt.error}</Alert>
      )}
    </div>
  );
}
