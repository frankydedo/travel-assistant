// Destinazioni mostrate nella landing (statiche: la landing non chiama API).
// Le classi Tailwind sono scritte per intero perché il compilatore le trova solo come stringhe letterali.
export interface LandingDestination {
  city: string;
  country: string;
  /** Pallino nella striscia delle destinazioni. */
  dot: string;
  /** Colore del segnaposto e dell'alone nell'illustrazione. */
  fill: string;
  pulse: string;
  /** Posizione nel viewBox dell'illustrazione (punta del segnaposto). */
  x: number;
  y: number;
  label: "left" | "right" | "below";
}

export const DESTINATIONS: LandingDestination[] = [
  { city: "Sicilia", country: "Italia", dot: "bg-amber-500", fill: "fill-amber-500", pulse: "fill-amber-400/50", x: 238, y: 248, label: "below" },
  { city: "Barcellona", country: "Spagna", dot: "bg-rose-500", fill: "fill-rose-500", pulse: "fill-rose-400/50", x: 194, y: 222, label: "left" },
  { city: "Atene", country: "Grecia", dot: "bg-sky-500", fill: "fill-sky-500", pulse: "fill-sky-300/50", x: 274, y: 234, label: "right" },
  { city: "Tokyo", country: "Giappone", dot: "bg-violet-500", fill: "fill-violet-500", pulse: "fill-violet-400/50", x: 394, y: 204, label: "right" },
  { city: "Reykjavik", country: "Islanda", dot: "bg-emerald-500", fill: "fill-emerald-500", pulse: "fill-emerald-400/50", x: 170, y: 130, label: "left" },
];
