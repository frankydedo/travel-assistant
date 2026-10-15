import type { ReactNode } from "react";
import { CalendarDays, Check, Heart, MapPin, PlaneTakeoff, Timer, Users, Wallet, X, type LucideIcon } from "lucide-react";
import type { ConversationDetail, RequirementField, TripRequirements } from "../api/types";
import { useCatalog, type CatalogLookup } from "../lib/catalog";
import { formatEUR, monthName, plural } from "../lib/format";
import { PhaseStepper } from "./PhaseStepper";
import { ProvenanceLegend } from "./Provenance";
import { Button } from "./ui/Button";
import { cn } from "./ui/cn";

const FIELDS: { key: RequirementField; label: string; icon: LucideIcon }[] = [
  { key: "budget_total", label: "Budget totale", icon: Wallet },
  { key: "destination", label: "Destinazione", icon: MapPin },
  { key: "preferences", label: "Preferenze", icon: Heart },
  { key: "month", label: "Mese", icon: CalendarDays },
  { key: "duration", label: "Durata", icon: Timer },
  { key: "departure_airport", label: "Partenza", icon: PlaneTakeoff },
  { key: "travelers", label: "Viaggiatori", icon: Users },
];

function formatField(req: TripRequirements, key: RequirementField, cat: CatalogLookup): string | null {
  switch (key) {
    case "budget_total":
      if (req.budget_total == null) return null;
      return req.budget_total === "unlimited" ? "Illimitato" : formatEUR(req.budget_total);
    case "destination": {
      const d = req.destination;
      if (!d) return null;
      if (d.type === "suggest") return "Consigliami tu";
      if (d.type === "anywhere") return "Ovunque";
      return d.country_code ? cat.countryName(d.country_code) : null;
    }
    case "preferences": {
      const p = req.preferences;
      if (!p) return null;
      if (p.categories.length === 0) return "Nessuna preferenza";
      const parts = [p.categories.map(cat.categoryLabel).join(", "), p.notes ?? ""].filter(Boolean);
      return parts.length ? parts.join(" · ") : "Nessuna preferenza";
    }
    case "month":
      return req.month == null ? null : monthName(req.month);
    case "duration": {
      const d = req.duration;
      if (!d) return null;
      return d.min_days === d.max_days
        ? plural(d.min_days, "giorno", "giorni")
        : `${d.min_days}-${d.max_days} giorni`;
    }
    case "departure_airport":
      if (!req.departure_airport) return null;
      return req.departure_airport === "ANY" ? "Qualsiasi aeroporto" : cat.airportLabel(req.departure_airport);
    case "travelers":
      return req.travelers == null ? null : String(req.travelers);
  }
}

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Requirements({ conversation }: { conversation: ConversationDetail }) {
  const cat = useCatalog();
  const missing = new Set(conversation.missing_fields);
  const rows = FIELDS.map((f) => {
    const value = formatField(conversation.requirements, f.key, cat);
    return { ...f, value, isMissing: missing.has(f.key) || value === null };
  });
  const collected = rows.filter((r) => !r.isMissing).length;
  const pct = Math.round((collected / rows.length) * 100);

  return (
    <Section
      title="Requisiti"
      aside={
        <span className="text-xs font-medium text-zinc-600 tabular-nums dark:text-zinc-300">
          {collected}/{rows.length} requisiti
        </span>
      }
    >
      <div
        role="progressbar"
        aria-label="Requisiti raccolti"
        aria-valuemin={0}
        aria-valuemax={rows.length}
        aria-valuenow={collected}
        className="mb-3 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-500", collected === rows.length ? "bg-emerald-500" : "bg-indigo-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <dl className="space-y-1">
        {rows.map(({ key, label, icon: Icon, value, isMissing }) => (
          <div
            key={key}
            className={cn("flex items-start gap-2.5 rounded-lg px-1.5 py-1.5", isMissing && "opacity-70")}
          >
            <span
              className={cn(
                "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md",
                isMissing
                  ? "border border-dashed border-zinc-300 text-zinc-400 dark:border-zinc-700 dark:text-zinc-500"
                  : "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
              )}
            >
              <Icon className="size-3.5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <dt className="text-[11px] text-zinc-500 dark:text-zinc-400">{label}</dt>
              <dd className={cn("text-sm break-words", isMissing ? "text-zinc-400 italic dark:text-zinc-500" : "font-medium")}>
                {isMissing ? "da raccogliere" : value}
              </dd>
            </div>
            {!isMissing && <Check className="mt-1.5 size-3.5 shrink-0 text-emerald-500" aria-label="raccolto" />}
          </div>
        ))}
      </dl>
    </Section>
  );
}

interface Props {
  conversation: ConversationDetail | null;
  /** Presente solo quando il pannello è aperto come drawer. */
  onClose?: () => void;
}

export function StatusPanel({ conversation, onClose }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-3">
        <h2 className="text-sm font-semibold">Stato della conversazione</h2>
        {onClose && (
          <Button variant="ghost" size="icon" className="xl:hidden" aria-label="Chiudi stato della conversazione" onClick={onClose}>
            <X className="size-4" aria-hidden />
          </Button>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-4">
        {conversation ? (
          <>
            <Section title="Fase">
              <PhaseStepper phase={conversation.phase} />
            </Section>
            <Requirements conversation={conversation} />
          </>
        ) : (
          <p className="rounded-2xl border border-dashed border-zinc-300 p-4 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
            Apri o crea una conversazione per vedere fase e requisiti raccolti.
          </p>
        )}
      </div>
      <div className="border-t border-zinc-200 p-4 dark:border-zinc-800">
        <ProvenanceLegend />
      </div>
    </div>
  );
}
