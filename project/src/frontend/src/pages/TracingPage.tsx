import { Activity, Clock, Coins, Cpu, GitBranch, Hash } from "lucide-react";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";

const METRICS = [
  { icon: Cpu, title: "Provider", text: "Quale modello ha risposto a ogni turno (Gemini, Groq, LM Studio o riserva)." },
  { icon: Hash, title: "Token", text: "Token di input e output per chiamata e per conversazione." },
  { icon: Clock, title: "Latenza", text: "Tempo di risposta di ogni chiamata LLM e del turno completo." },
  { icon: GitBranch, title: "Fallback", text: "Quando e perché la catena è passata al provider successivo." },
  { icon: Coins, title: "Costi stimati", text: "Stima del costo per turno, per conversazione e per provider." },
];

export function TracingPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
        <Card className="overflow-hidden">
          <div className="border-b border-zinc-100 bg-linear-to-br from-indigo-50 via-white to-violet-50 px-6 py-10 text-center dark:border-zinc-800 dark:from-indigo-500/10 dark:via-zinc-900 dark:to-violet-500/10">
            <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-white text-indigo-600 shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-indigo-300 dark:ring-zinc-700">
              <Activity className="size-7" aria-hidden />
            </span>
            <Badge tone="indigo" className="mt-5">
              In arrivo
            </Badge>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">Tracing e osservabilità</h1>
            <p className="mx-auto mt-2 max-w-lg text-sm text-zinc-600 dark:text-zinc-400">
              Disponibile nella fase di osservabilità: le metriche delle chiamate LLM verranno lette da Langfuse e
              mostrate qui, turno per turno.
            </p>
          </div>
          <ul className="grid gap-px bg-zinc-100 sm:grid-cols-2 lg:grid-cols-3 dark:bg-zinc-800">
            {METRICS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="bg-white p-5 dark:bg-zinc-900">
                <div className="flex items-center gap-2">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <h2 className="text-sm font-semibold">{title}</h2>
                </div>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{text}</p>
              </li>
            ))}
            <li className="hidden bg-white p-5 lg:block dark:bg-zinc-900" aria-hidden />
          </ul>
        </Card>
      </div>
    </div>
  );
}
