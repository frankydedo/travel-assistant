import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, ChevronDown, Luggage, MapPin, MessagesSquare, TriangleAlert, Users, XCircle } from "lucide-react";
import { cancelBooking, errorMessage, listBookings } from "../api/client";
import type { Booking } from "../api/types";
import { ItineraryCard } from "../components/ItineraryCard";
import { ComputedMarker } from "../components/Provenance";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { Skeleton } from "../components/ui/Skeleton";
import { cn } from "../components/ui/cn";
import { formatDate, formatDateTime, formatEUR, plural, VARIANT_LABELS } from "../lib/format";
import { VARIANT_STYLE } from "../lib/styles";

const STATUS_LABELS: Record<Booking["status"], string> = {
  confirmed: "Confermata",
  cancelled: "Annullata",
};

function BookingCard({
  booking: b,
  cancelling,
  disabled,
  onCancel,
}: {
  booking: Booking;
  cancelling: boolean;
  disabled: boolean;
  onCancel: () => void;
}) {
  const it = b.itinerary;
  const v = VARIANT_STYLE[it.variant];
  const cancelled = b.status === "cancelled";
  return (
    <Card className={cn("flex flex-col", cancelled && "opacity-75")}>
      <div className={cn("h-1.5 rounded-t-2xl", cancelled ? "bg-zinc-300 dark:bg-zinc-700" : v.stripe)} aria-hidden />
      <div className="p-5">
        <div className="flex items-center justify-between gap-2">
          <Badge tone={cancelled ? "neutral" : "emerald"}>{STATUS_LABELS[b.status]}</Badge>
          <span className={cn("text-xs font-semibold tracking-wide uppercase", v.text)}>
            {VARIANT_LABELS[it.variant]}
          </span>
        </div>
        <h3 className="mt-3 flex items-center gap-1.5 text-lg font-semibold">
          <MapPin className="size-4 shrink-0 text-zinc-400" aria-hidden />
          <span className={cn("truncate", cancelled && "line-through decoration-zinc-400")}>
            {it.destination}, {it.country_name}
          </span>
        </h3>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-600 dark:text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="size-3.5" aria-hidden />
            {formatDate(it.start_date)} – {formatDate(it.end_date)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Users className="size-3.5" aria-hidden />
            {plural(it.travelers, "viaggiatore", "viaggiatori")}
          </span>
        </div>

        <div className="mt-4 flex items-end justify-between gap-3">
          <div>
            <div className="text-2xl font-bold tracking-tight tabular-nums">{formatEUR(b.total_price)}</div>
            <ComputedMarker label="Prezzo salvato alla prenotazione" />
          </div>
          {!cancelled && (
            <Button
              variant="danger-soft"
              size="sm"
              disabled={disabled}
              loading={cancelling}
              icon={<XCircle className="size-3.5" aria-hidden />}
              onClick={onCancel}
            >
              {cancelling ? "Annullamento…" : "Annulla"}
            </Button>
          )}
        </div>
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          Prenotata il {formatDateTime(b.created_at)}
          {b.cancelled_at && <> · annullata il {formatDateTime(b.cancelled_at)}</>}
        </p>
      </div>

      <details className="group/detail border-t border-zinc-100 dark:border-zinc-800">
        <summary className="flex cursor-pointer items-center justify-between rounded-b-2xl px-5 py-3 text-sm font-medium select-none hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          Dettaglio itinerario
          <ChevronDown className="size-4 transition-transform group-open/detail:rotate-180" aria-hidden />
        </summary>
        <div className="px-3 pb-3">
          <ItineraryCard itinerary={it} className="shadow-none dark:shadow-none" />
        </div>
      </details>
    </Card>
  );
}

export function BookingsPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [toCancel, setToCancel] = useState<Booking | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listBookings();
      setBookings([...list].sort((a, b) => b.created_at.localeCompare(a.created_at)));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCancel(b: Booking) {
    setToCancel(null);
    setCancellingId(b.id);
    setError(null);
    try {
      await cancelBooking(b.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCancellingId(null);
      await refresh();
    }
  }

  const active = bookings?.filter((b) => b.status === "confirmed").length ?? 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Le mie prenotazioni</h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              {bookings === null
                ? "Caricamento…"
                : `${plural(bookings.length, "prenotazione", "prenotazioni")} · ${plural(active, "attiva", "attive")}`}
            </p>
          </div>
        </header>

        {error && <Alert className="mb-4" onDismiss={() => setError(null)}>{error}</Alert>}

        {bookings === null && !error && (
          <div className="grid gap-4 md:grid-cols-2" aria-label="Caricamento prenotazioni">
            {[0, 1].map((i) => (
              <Card key={i} className="space-y-3 p-5">
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-8 w-32" />
              </Card>
            ))}
          </div>
        )}

        {bookings?.length === 0 && (
          <Card className="mx-auto flex max-w-lg flex-col items-center px-6 py-14 text-center">
            <span className="relative flex size-16 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
              <Luggage className="size-8" aria-hidden />
              <span className="absolute -top-1.5 -right-1.5 size-4 rounded-full bg-violet-400/70" aria-hidden />
              <span className="absolute -bottom-1 -left-2 size-2.5 rounded-full bg-sky-400/70" aria-hidden />
            </span>
            <h2 className="mt-5 text-lg font-semibold">Nessuna prenotazione, per ora</h2>
            <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
              Racconta all'assistente il viaggio che hai in mente: ti proporrà tre varianti entro il budget.
            </p>
            <Link
              to="/"
              className="mt-6 inline-flex h-10 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400"
            >
              <MessagesSquare className="size-4" aria-hidden />
              Inizia una chat
            </Link>
          </Card>
        )}

        {bookings && bookings.length > 0 && (
          <ul className="grid items-start gap-4 md:grid-cols-2">
            {bookings.map((b) => (
              <li key={b.id}>
                <BookingCard
                  booking={b}
                  cancelling={cancellingId === b.id}
                  disabled={cancellingId !== null}
                  onCancel={() => setToCancel(b)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={toCancel !== null}
        tone="danger"
        icon={
          <span className="flex size-10 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300">
            <TriangleAlert className="size-5" aria-hidden />
          </span>
        }
        title="Annullare la prenotazione?"
        description={
          toCancel && (
            <>
              Stai per annullare il viaggio a{" "}
              <strong className="text-zinc-900 dark:text-zinc-100">
                {toCancel.itinerary.destination} ({formatDate(toCancel.itinerary.start_date)})
              </strong>
              . Voli, hotel e attività tornano disponibili.
            </>
          )
        }
        confirmLabel="Sì, annulla"
        cancelLabel="Mantieni"
        onConfirm={() => toCancel && void handleCancel(toCancel)}
        onCancel={() => setToCancel(null)}
      />
    </div>
  );
}
