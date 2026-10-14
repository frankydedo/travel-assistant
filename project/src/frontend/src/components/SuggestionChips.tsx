import { Lightbulb } from "lucide-react";

export const SUGGESTIONS = [
  "Siamo in due, 2500 €, Grecia ad agosto per 5-7 giorni da Napoli: mare e vita notturna",
  "Consigliami tu: 1500 €, giugno, una settimana da Roma, cultura e cibo",
  "Islanda a febbraio, 4 giorni, da Milano, natura, da solo, 1800 €",
  "Portogallo a maggio, 3 viaggiatori, 6 giorni da Bologna, 3000 €, spiagge e cucina",
];

export function SuggestionChips({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
        <Lightbulb className="size-3.5" aria-hidden />
        Prova con un esempio
      </p>
      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="max-w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-left text-sm text-zinc-700 shadow-xs transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-indigo-500/40 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-200"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
