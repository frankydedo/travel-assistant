import type { ItineraryStatus, ItineraryVariant, Phase, Provider } from "../api/types";

const eur = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

export const formatEUR = (n: number): string => eur.format(n);

/** "YYYY-MM-DD" interpretata come data locale (evita slittamenti di fuso). */
function parseDate(s: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(s);
}

export const formatDate = (s: string): string =>
  parseDate(s).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });

export const formatDayDate = (s: string): string =>
  parseDate(s).toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" });

export const formatDateTime = (s: string): string =>
  new Date(s).toLocaleString("it-IT", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** Orario di volo: accetta "HH:MM", "HH:MM:SS" o un datetime ISO. */
export function formatTime(s: string): string {
  if (s.includes("T")) {
    return new Date(s).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  }
  return s.slice(0, 5);
}

const MONTHS = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

export function monthName(m: number): string {
  const name = MONTHS[m - 1];
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : String(m);
}

export const PHASES: Phase[] = [
  "COLLECTING_REQUIREMENTS",
  "PROPOSING",
  "AWAITING_CONFIRMATION",
  "BOOKED",
];

export const PHASE_LABELS: Record<Phase, string> = {
  COLLECTING_REQUIREMENTS: "Raccolta requisiti",
  PROPOSING: "Proposta",
  AWAITING_CONFIRMATION: "Attesa conferma",
  BOOKED: "Prenotato",
};

export const VARIANT_LABELS: Record<ItineraryVariant, string> = {
  economy: "Economica",
  balanced: "Bilanciata",
  premium: "Premium",
};

export const ITINERARY_STATUS_LABELS: Record<ItineraryStatus, string> = {
  proposed: "Proposta",
  selected: "Scelta",
  booked: "Prenotata",
  discarded: "Scartata",
};

export const PROVIDERS: Provider[] = ["GEMINI", "GROQ", "MOCK", "SYSTEM"];

export const plural = (n: number, one: string, many: string): string =>
  `${n} ${n === 1 ? one : many}`;

export const formatClock = (s: string): string =>
  new Date(s).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });

const rtf = new Intl.RelativeTimeFormat("it-IT", { numeric: "auto" });

/** Tempo relativo breve ("5 minuti fa", "ieri"); oltre una settimana mostra la data. */
export function formatRelative(s: string, now: number = Date.now()): string {
  const diffSec = Math.round((new Date(s).getTime() - now) / 1000);
  const abs = Math.abs(diffSec);
  if (abs < 45) return "adesso";
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  if (abs < 7 * 86400) return rtf.format(Math.round(diffSec / 86400), "day");
  return new Date(s).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}
