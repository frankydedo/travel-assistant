import {
  BedDouble,
  CalendarDays,
  ChevronDown,
  Clock,
  MapPin,
  Moon,
  Plane,
  PlaneLanding,
  PlaneTakeoff,
  Star,
  Sun,
  Ticket,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import type { DayPlan, Flight, Itinerary } from "../api/types";
import { useCatalog } from "../lib/catalog";
import {
  formatDate,
  formatDayDate,
  formatEUR,
  formatTime,
  ITINERARY_STATUS_LABELS,
  plural,
  VARIANT_LABELS,
} from "../lib/format";
import { ITINERARY_STATUS_TONE, VARIANT_STYLE } from "../lib/styles";
import { AiMarker, ComputedMarker } from "./Provenance";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { cn } from "./ui/cn";

interface Props {
  itinerary: Itinerary;
  /** Se presente e abilitato mostra il pulsante "Scegli questa". */
  onSelect?: () => void;
  canSelect?: boolean;
  /** Una selezione è in corso (su questa o su un'altra card): pulsante disabilitato. */
  busy?: boolean;
  /** La selezione in corso è proprio questa card. */
  selecting?: boolean;
  className?: string;
}

function Chip({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
      {icon}
      {children}
    </span>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h5 className="mb-2 text-[11px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
      {children}
    </h5>
  );
}

function BudgetBar({
  total,
  budget,
  barClass,
}: {
  total: number;
  budget: number;
  barClass: string;
}) {
  const pct = budget > 0 ? Math.round((total / budget) * 100) : 0;
  const over = total > budget;
  return (
    <div>
      <div
        role="meter"
        aria-label="Totale rispetto al budget"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(pct, 100)}
        className="h-2 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width]",
            over ? "bg-rose-500" : barClass,
          )}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-xs text-zinc-500 dark:text-zinc-400">
        <span
          className={cn(over && "font-medium text-rose-600 dark:text-rose-400")}
        >
          {pct}% del budget
        </span>
        <span>
          {over ? "oltre di " : "margine "}
          <span className="font-medium text-zinc-700 tabular-nums dark:text-zinc-200">
            {formatEUR(Math.abs(budget - total))}
          </span>
        </span>
      </div>
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl bg-zinc-50 px-2.5 py-2 dark:bg-zinc-800/60">
      <div className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
        {icon}
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums">
        {formatEUR(value)}
      </div>
    </div>
  );
}

function FlightRoute({
  label,
  icon,
  flight,
}: {
  label: string;
  icon: ReactNode;
  flight: Flight;
}) {
  const { airportLabel } = useCatalog();
  return (
    <div className="rounded-xl border border-zinc-100 bg-zinc-50/70 p-3 dark:border-zinc-800 dark:bg-zinc-800/40">
      <div className="flex items-center justify-between gap-2 text-[11px] text-zinc-500 dark:text-zinc-400">
        <span className="inline-flex items-center gap-1 font-medium text-zinc-600 dark:text-zinc-300">
          {icon}
          {label} · {formatDate(flight.date)}
        </span>
        <span className="truncate tabular-nums">
          {flight.flight_number} · {flight.carrier}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div>
          <abbr
            title={airportLabel(flight.origin)}
            className="text-base font-semibold no-underline"
          >
            {flight.origin}
          </abbr>
          <div className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
            {formatTime(flight.departure_time)}
          </div>
        </div>
        <div
          className="flex flex-1 items-center gap-1 text-zinc-300 dark:text-zinc-600"
          aria-hidden
        >
          <span className="h-px flex-1 border-t border-dashed border-current" />
          <Plane className="size-3.5 rotate-45 text-zinc-400 dark:text-zinc-500" />
          <span className="h-px flex-1 border-t border-dashed border-current" />
        </div>
        <div className="text-right">
          <abbr
            title={airportLabel(flight.destination)}
            className="text-base font-semibold no-underline"
          >
            {flight.destination}
          </abbr>
          <div className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
            {formatTime(flight.arrival_time)}
          </div>
        </div>
      </div>
      <div className="mt-1.5 text-[11px] text-zinc-500 tabular-nums dark:text-zinc-400">
        {formatEUR(flight.price_per_person)} a persona · totale{" "}
        {formatEUR(flight.subtotal)}
      </div>
    </div>
  );
}

function Stars({ n }: { n: number }) {
  const count = Math.max(0, Math.round(n));
  return (
    <span className="inline-flex items-center" aria-label={`${count} stelle`}>
      {Array.from({ length: count }, (_, i) => (
        <Star
          key={i}
          className="size-3 fill-amber-400 text-amber-400"
          aria-hidden
        />
      ))}
    </span>
  );
}

function DayItem({
  d,
  last,
  dotClass,
}: {
  d: DayPlan;
  last: boolean;
  dotClass: string;
}) {
  const { categoryLabel } = useCatalog();
  const a = d.activity;
  return (
    <li className="relative grid grid-cols-[1.5rem_1fr] gap-3">
      <div className="flex flex-col items-center">
        <span
          className={cn(
            "z-10 flex size-6 items-center justify-center rounded-full text-[11px] font-semibold text-white ring-4 ring-white dark:ring-zinc-900",
            dotClass,
          )}
        >
          {d.day}
        </span>
        {!last && (
          <span
            className="w-px flex-1 bg-zinc-200 dark:bg-zinc-700"
            aria-hidden
          />
        )}
      </div>
      <div className={cn("min-w-0", !last && "pb-4")}>
        <div className="text-[11px] text-zinc-500 capitalize dark:text-zinc-400">
          Giorno {d.day} · {formatDayDate(d.date)}
        </div>
        {d.travel_note && (
          <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            <Plane className="size-3" aria-hidden />
            {d.travel_note}
          </div>
        )}
        {!a ? (
          <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-300">
            Giorno di viaggio: con questi orari dei voli non c'è tempo per
            un'attività.
          </p>
        ) : (
          <DayActivity a={a} categoryLabel={categoryLabel} />
        )}
      </div>
    </li>
  );
}

function DayActivity({
  a,
  categoryLabel,
}: {
  a: NonNullable<DayPlan["activity"]>;
  categoryLabel: (category: string) => string;
}) {
  return (
    <>
      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-medium">{a.name}</span>
        <Badge tone="neutral">{categoryLabel(a.category)}</Badge>
      </div>
      {a.description && (
        <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">
          {a.description_ai_generated && (
            <AiMarker
              label="Descrizione generata con AI e rivista"
              className="mr-1 align-[-3px]"
            />
          )}
          {a.description}
        </p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-zinc-500 tabular-nums dark:text-zinc-400">
        <span className="inline-flex items-center gap-1">
          <Clock className="size-3" aria-hidden />
          {a.duration_hours} h
        </span>
        <span>{formatEUR(a.price_per_person)} a persona</span>
        <span className="font-medium text-zinc-700 dark:text-zinc-200">
          totale {formatEUR(a.subtotal)}
        </span>
      </div>
    </>
  );
}

export function ItineraryCard({
  itinerary: it,
  onSelect,
  canSelect = false,
  busy = false,
  selecting = false,
  className,
}: Props) {
  const v = VARIANT_STYLE[it.variant];
  return (
    <article
      className={cn(
        "flex flex-col rounded-2xl border border-zinc-200 bg-white shadow-md shadow-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-black/30",
        it.status === "selected" && "ring-2 ring-indigo-500/70",
        it.status === "booked" && "ring-2 ring-emerald-500/70",
        it.status === "discarded" && "opacity-60",
        className,
      )}
    >
      <div className={cn("h-1.5 rounded-t-2xl", v.stripe)} aria-hidden />
      <div className="flex flex-1 flex-col gap-4 p-4">
        <header className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase",
                v.text,
              )}
            >
              <span className={cn("size-2 rounded-full", v.dot)} aria-hidden />
              {VARIANT_LABELS[it.variant]}
            </span>
            <h4 className="mt-1 flex items-center gap-1.5 text-lg leading-tight font-semibold">
              <MapPin className="size-4 shrink-0 text-zinc-400" aria-hidden />
              <span className="truncate">
                {it.destination}, {it.country_name}
              </span>
            </h4>
          </div>
          {it.status !== "proposed" && (
            <Badge tone={ITINERARY_STATUS_TONE[it.status]}>
              {ITINERARY_STATUS_LABELS[it.status]}
            </Badge>
          )}
        </header>

        <div className="flex flex-wrap gap-1.5">
          <Chip icon={<CalendarDays className="size-3" aria-hidden />}>
            {formatDate(it.start_date)} – {formatDate(it.end_date)}
          </Chip>
          <Chip icon={<Sun className="size-3" aria-hidden />}>
            {plural(it.days, "giorno", "giorni")}
          </Chip>
          <Chip icon={<Moon className="size-3" aria-hidden />}>
            {plural(it.nights, "notte", "notti")}
          </Chip>
          <Chip icon={<Users className="size-3" aria-hidden />}>
            {plural(it.travelers, "viaggiatore", "viaggiatori")} ·{" "}
            {plural(it.rooms, "camera", "camere")}
          </Chip>
        </div>

        <section aria-label="Prezzo">
          <div className="flex items-end justify-between gap-2">
            <div>
              <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
                Totale per il gruppo
              </div>
              <div className="text-3xl font-bold tracking-tight tabular-nums">
                {formatEUR(it.total_price)}
              </div>
            </div>
            <div className="pb-1 text-right text-xs text-zinc-500 dark:text-zinc-400">
              {it.budget_total == null ? (
                "budget illimitato"
              ) : (
                <>
                  budget{" "}
                  <span className="tabular-nums">
                    {formatEUR(it.budget_total)}
                  </span>
                </>
              )}
            </div>
          </div>
          {it.budget_total != null && (
            <div className="mt-2">
              <BudgetBar
                total={it.total_price}
                budget={it.budget_total}
                barClass={v.bar}
              />
            </div>
          )}
          <div className="mt-3 grid grid-cols-3 gap-2">
            <StatTile
              icon={<Plane className="size-3" aria-hidden />}
              label="Voli"
              value={it.cost_breakdown.flights}
            />
            <StatTile
              icon={<BedDouble className="size-3" aria-hidden />}
              label="Hotel"
              value={it.cost_breakdown.hotel}
            />
            <StatTile
              icon={<Ticket className="size-3" aria-hidden />}
              label="Attività"
              value={it.cost_breakdown.activities}
            />
          </div>
          <div className="mt-2">
            <ComputedMarker />
          </div>
        </section>

        <section>
          <SectionTitle>Voli</SectionTitle>
          <div className="space-y-2">
            <FlightRoute
              label="Andata"
              icon={<PlaneTakeoff className="size-3" aria-hidden />}
              flight={it.flights.outbound}
            />
            <FlightRoute
              label="Ritorno"
              icon={<PlaneLanding className="size-3" aria-hidden />}
              flight={it.flights.return}
            />
          </div>
        </section>

        <section>
          <SectionTitle>Hotel</SectionTitle>
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              <BedDouble className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium">{it.hotel.name}</span>
                <Stars n={it.hotel.stars} />
              </div>
              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                {it.hotel.neighborhood} ·{" "}
                {plural(it.hotel.nights, "notte", "notti")} · media{" "}
                <span className="tabular-nums">
                  {formatEUR(it.hotel.price_per_night_avg)}
                </span>
                /notte
              </div>
            </div>
            <span className="text-sm font-semibold tabular-nums">
              {formatEUR(it.hotel.subtotal)}
            </span>
          </div>
        </section>

        <details className="group/days rounded-xl border border-zinc-200 dark:border-zinc-800">
          <summary className="flex cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-sm font-medium select-none hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
            <span>Programma giorno per giorno</span>
            <span className="flex items-center gap-1.5 text-xs font-normal text-zinc-500 dark:text-zinc-400">
              {plural(
                it.days_plan.filter((d) => d.activity).length,
                "attività",
                "attività",
              )}
              <ChevronDown
                className="size-4 transition-transform group-open/days:rotate-180"
                aria-hidden
              />
            </span>
          </summary>
          <ol className="px-3 pt-1 pb-3">
            {it.days_plan.map((d, i) => (
              <DayItem
                key={d.day}
                d={d}
                last={i === it.days_plan.length - 1}
                dotClass={v.dot}
              />
            ))}
          </ol>
        </details>

        {onSelect && canSelect && (
          <Button
            className="mt-auto w-full"
            onClick={onSelect}
            disabled={busy}
            loading={selecting}
          >
            {selecting ? "Selezione…" : "Scegli questa"}
          </Button>
        )}
      </div>
    </article>
  );
}
