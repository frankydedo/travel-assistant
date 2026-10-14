// Mappe di stile condivise (classi Tailwind statiche, così il compilatore le vede).
import type { ItineraryStatus, ItineraryVariant, Phase } from "../api/types";
import type { Tone } from "../components/ui/Badge";

export const VARIANT_STYLE: Record<
  ItineraryVariant,
  { stripe: string; text: string; bar: string; dot: string; ring: string }
> = {
  economy: {
    stripe: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
    bar: "bg-emerald-500",
    dot: "bg-emerald-500",
    ring: "ring-emerald-500",
  },
  balanced: {
    stripe: "bg-sky-500",
    text: "text-sky-700 dark:text-sky-300",
    bar: "bg-sky-500",
    dot: "bg-sky-500",
    ring: "ring-sky-500",
  },
  premium: {
    stripe: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
    bar: "bg-amber-500",
    dot: "bg-amber-500",
    ring: "ring-amber-500",
  },
};

export const PHASE_TONE: Record<Phase, Tone> = {
  COLLECTING_REQUIREMENTS: "neutral",
  PROPOSING: "indigo",
  AWAITING_CONFIRMATION: "amber",
  BOOKED: "emerald",
};

export const ITINERARY_STATUS_TONE: Record<ItineraryStatus, Tone> = {
  proposed: "neutral",
  selected: "indigo",
  booked: "emerald",
  discarded: "neutral",
};
