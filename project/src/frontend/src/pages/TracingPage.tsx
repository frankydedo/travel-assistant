// Pagina di tracing: metriche delle chiamate LLM delle conversazioni dell'utente, lette da Langfuse.
// Solo lettura e solo visualizzazione: i numeri arrivano già aggregati dal backend.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Clock,
  Coins,
  Cpu,
  ExternalLink,
  Hash,
  KeyRound,
  ListTree,
  MessagesSquare,
  RefreshCw,
  RotateCcw,
  ServerOff,
  Sparkles,
  Terminal,
} from "lucide-react";
import { errorMessage, getTracingSummary } from "../api/client";
import type {
  TracingModelRow,
  TracingPeriod,
  TracingSeriesPoint,
  TracingSummary,
  TracingSummaryAvailable,
} from "../api/types";
import { Alert } from "../components/ui/Alert";
import { Badge, type Tone } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";
import { cn } from "../components/ui/cn";
import { formatClock, formatDateTime, formatRelative } from "../lib/format";

const LANGFUSE_URL = "http://localhost:3001";
const REFRESH_MS = 30_000;

const PERIODS: { value: TracingPeriod; label: string }[] = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7 giorni" },
  { value: "30d", label: "30 giorni" },
];

// --- Formattazione -----------------------------------------------------------

const intFmt = new Intl.NumberFormat("it-IT");
const compactFmt = new Intl.NumberFormat("it-IT", { notation: "compact", maximumFractionDigits: 1 });
const pctFmt = new Intl.NumberFormat("it-IT", { style: "percent", maximumFractionDigits: 1 });

const formatInt = (n: number) => intFmt.format(Math.round(n));
const formatCompact = (n: number) => (Math.abs(n) < 10_000 ? formatInt(n) : compactFmt.format(n));

/** Dollari con al massimo 4 decimali significativi per gli importi piccoli: $0,0013. */
function formatUSD(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "$0";
  if (Math.abs(n) < 0.0001) return "< $0,0001";
  const opts: Intl.NumberFormatOptions =
    Math.abs(n) >= 1
      ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 4 };
  return `$${new Intl.NumberFormat("it-IT", opts).format(n)}`;
}

function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: ms < 10_000 ? 2 : 1 }).format(ms / 1000)} s`;
}

/** Etichetta breve del bucket: "14 ott" per i giorni, "15:00" per le ore. */
function bucketLabel(bucket: string, long = false): string {
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(bucket);
  if (day) {
    const d = new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]));
    return d.toLocaleDateString("it-IT", long ? { weekday: "short", day: "numeric", month: "short" } : { day: "numeric", month: "short" });
  }
  const d = new Date(bucket);
  if (Number.isNaN(d.getTime())) return bucket;
  return long
    ? d.toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

// --- Etichette ---------------------------------------------------------------

const TASK_LABELS: Record<string, string> = {
  extract_requirements: "Estrazione requisiti",
  proposal_tools: "Tool di proposta",
  choose_destination: "Scelta destinazione",
};

function taskLabel(task: string): string {
  if (TASK_LABELS[task]) return TASK_LABELS[task];
  if (task.startsWith("reply:")) return `Risposta: ${task.slice("reply:".length).replace(/_/g, " ")}`;
  return task;
}

const TURN_LABELS: Record<string, string> = {
  chat_turn: "Messaggio",
  select_itinerary: "Selezione variante",
  replan_after_conflict: "Ripianificazione",
};

const LEVEL_TONE: Record<string, Tone> = {
  DEFAULT: "neutral",
  DEBUG: "neutral",
  WARNING: "amber",
  ERROR: "rose",
};

const LEVEL_LABELS: Record<string, string> = {
  DEFAULT: "ok",
  DEBUG: "debug",
  WARNING: "avviso",
  ERROR: "errore",
};

// --- Componenti piccoli ------------------------------------------------------

const PILL = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset";

/** Badge del provider con lo stesso linguaggio dei marcatori di provenienza della chat. */
function ProviderBadge({ provider }: { provider: TracingModelRow["provider"] }) {
  if (provider === "GROQ" || provider === "GEMINI") {
    return (
      <span
        className={cn(
          PILL,
          "bg-linear-to-r from-violet-50 to-indigo-50 text-violet-700 ring-violet-200 dark:from-violet-500/15 dark:to-indigo-500/15 dark:text-violet-200 dark:ring-violet-400/30",
        )}
      >
        <Sparkles className="size-3" aria-hidden />
        {provider}
      </span>
    );
  }
  if (provider === "MOCK") {
    return (
      <span className={cn(PILL, "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700")}>
        <Cpu className="size-3" aria-hidden />
        MOCK · regole
      </span>
    );
  }
  return <span className={cn(PILL, "text-zinc-500 ring-zinc-200 dark:text-zinc-400 dark:ring-zinc-700")}>—</span>;
}

function ExternalA({ href, children, className, label }: { href: string; children: ReactNode; className?: string; label?: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} className={className}>
      {children}
    </a>
  );
}

function SectionCard({
  icon: Icon,
  title,
  subtitle,
  children,
  className,
}: {
  icon: typeof Activity;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex min-w-0 flex-col", className)}>
      <div className="flex items-start gap-2.5 border-b border-zinc-100 px-5 py-3.5 dark:border-zinc-800">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          <Icon className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
        </div>
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </Card>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
  tone = "neutral",
}: {
  icon: typeof Activity;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "warn";
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </div>
      <div
        className={cn(
          "mt-1.5 text-2xl font-semibold tracking-tight tabular-nums",
          tone === "warn" && "text-amber-700 dark:text-amber-300",
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500 tabular-nums dark:text-zinc-400">{sub}</div>}
    </Card>
  );
}

function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="px-5 py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">{children}</p>;
}

// --- Grafico del costo nel tempo (SVG inline) --------------------------------

function useWidth() {
  const [width, setWidth] = useState(0);
  const ro = useRef<ResizeObserver | null>(null);
  // Callback ref: funziona anche se l'elemento compare dopo il primo render.
  const ref = useCallback((el: HTMLDivElement | null) => {
    ro.current?.disconnect();
    ro.current = null;
    if (!el) return;
    setWidth(el.clientWidth);
    ro.current = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    ro.current.observe(el);
  }, []);
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, width] as const;
}

/** Valore "tondo" per il massimo dell'asse y (1, 2, 5 × 10^k). */
function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = 10 ** exp;
  const f = v / base;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nice * base;
}

/** Path di una barra con angoli superiori arrotondati e base piatta sulla linea zero. */
function barPath(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

function CostChart({ series }: { series: TracingSeriesPoint[] }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const total = series.reduce((s, p) => s + p.cost_usd, 0);
  const allZero = series.length === 0 || series.every((p) => p.cost_usd === 0);

  if (allZero) {
    return (
      <EmptyNote>
        Nessun costo nel periodo. Le chiamate al provider deterministico (MOCK) e quelle senza prezzo di listino valgono $0.
      </EmptyNote>
    );
  }

  const H = 180;
  const padL = 52;
  const padR = 8;
  const padT = 10;
  const padB = 24;
  const plotW = Math.max(0, width - padL - padR);
  const plotH = H - padT - padB;
  const max = niceMax(Math.max(...series.map((p) => p.cost_usd)));
  const slot = series.length > 0 ? plotW / series.length : 0;
  const gap = Math.min(4, slot * 0.25);
  const barW = Math.max(1, Math.min(28, slot - gap));
  const labelEvery = Math.max(1, Math.ceil(series.length / Math.max(1, Math.floor(plotW / 56))));
  const ticks = [0, 0.5, 1].map((f) => f * max);
  const active = hover !== null ? series[hover] : undefined;

  return (
    <div className="px-5 pt-3 pb-4">
      <div className="mb-2 flex min-h-5 flex-wrap items-baseline justify-between gap-x-3 text-xs text-zinc-500 dark:text-zinc-400">
        {active ? (
          <span className="tabular-nums">
            <span className="font-medium text-zinc-800 dark:text-zinc-100">{bucketLabel(active.bucket, true)}</span> ·{" "}
            {formatUSD(active.cost_usd)} · {formatInt(active.calls)} {active.calls === 1 ? "chiamata" : "chiamate"}
          </span>
        ) : (
          <span>Passa sopra una barra per i dettagli</span>
        )}
        <span className="tabular-nums">Totale {formatUSD(total)}</span>
      </div>
      <div ref={ref} className="w-full">
        {width > 0 && (
          <svg
            width={width}
            height={H}
            viewBox={`0 0 ${width} ${H}`}
            role="img"
            aria-label={`Costo stimato nel tempo, totale ${formatUSD(total)}`}
            className="block overflow-visible"
            onMouseLeave={() => setHover(null)}
          >
            {ticks.map((t) => {
              const y = padT + plotH - (t / max) * plotH;
              return (
                <g key={t}>
                  <line
                    x1={padL}
                    x2={width - padR}
                    y1={y}
                    y2={y}
                    className={t === 0 ? "stroke-zinc-300 dark:stroke-zinc-700" : "stroke-zinc-100 dark:stroke-zinc-800"}
                    strokeWidth={1}
                  />
                  <text
                    x={padL - 8}
                    y={y}
                    dy="0.32em"
                    textAnchor="end"
                    className="fill-zinc-500 text-[10px] tabular-nums dark:fill-zinc-400"
                  >
                    {formatUSD(t)}
                  </text>
                </g>
              );
            })}
            {series.map((p, i) => {
              const h = (p.cost_usd / max) * plotH;
              const cx = padL + slot * i + slot / 2;
              const x = cx - barW / 2;
              const y = padT + plotH - h;
              const isHover = hover === i;
              return (
                <g key={p.bucket} onMouseEnter={() => setHover(i)}>
                  <title>
                    {`${bucketLabel(p.bucket, true)}: ${formatUSD(p.cost_usd)} · ${formatInt(p.calls)} ${p.calls === 1 ? "chiamata" : "chiamate"}`}
                  </title>
                  {/* Area di hover a tutta altezza: anche le barre basse sono facili da puntare. */}
                  <rect
                    x={padL + slot * i}
                    y={padT}
                    width={slot}
                    height={plotH}
                    className={isHover ? "fill-zinc-100 dark:fill-zinc-800/60" : "fill-transparent"}
                  />
                  {h > 0 && (
                    <path
                      d={barPath(x, y, barW, Math.max(h, 1.5), 4)}
                      className={cn(
                        "transition-colors",
                        isHover ? "fill-indigo-500 dark:fill-indigo-300" : "fill-indigo-400 dark:fill-indigo-400",
                      )}
                    />
                  )}
                  {i % labelEvery === 0 && (
                    <text
                      x={cx}
                      y={H - 6}
                      textAnchor="middle"
                      className="fill-zinc-500 text-[10px] dark:fill-zinc-400"
                    >
                      {bucketLabel(p.bucket)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}

// --- Tabella per provider e modello ------------------------------------------

function ModelTable({ rows }: { rows: TracingModelRow[] }) {
  if (rows.length === 0) return <EmptyNote>Nessuna chiamata LLM nel periodo.</EmptyNote>;
  const totalCalls = rows.reduce((s, r) => s + r.calls, 0) || 1;
  const sorted = [...rows].sort((a, b) => b.calls - a.calls);
  const th = "px-3 py-2 text-right text-[11px] font-semibold tracking-wide whitespace-nowrap text-zinc-500 uppercase dark:text-zinc-400";
  const td = "px-3 py-2.5 text-right tabular-nums whitespace-nowrap";
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] text-sm">
        <thead className="border-b border-zinc-100 dark:border-zinc-800">
          <tr>
            <th className={cn(th, "pl-5 text-left")}>Provider · modello</th>
            <th className={th}>Chiamate</th>
            <th className={th}>Falliti</th>
            <th className={th}>Token in / out</th>
            <th className={th}>Costo</th>
            <th className={cn(th, "pr-5")}>Latenza media / p95</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {sorted.map((r) => {
            const share = r.calls / totalCalls;
            return (
              <tr key={`${r.provider}-${r.model}`} className="hover:bg-zinc-50/70 dark:hover:bg-zinc-800/30">
                <td className="py-2.5 pr-3 pl-5 align-top">
                  <div className="flex min-w-0 items-center gap-2">
                    <ProviderBadge provider={r.provider} />
                    <span className="truncate font-mono text-xs text-zinc-700 dark:text-zinc-300" title={r.model}>
                      {r.model}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2" title={`${pctFmt.format(share)} delle chiamate`}>
                    <div className="h-1.5 w-full max-w-48 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          r.provider === "MOCK" || r.provider === "—" ? "bg-zinc-400 dark:bg-zinc-500" : "bg-violet-500 dark:bg-violet-400",
                        )}
                        style={{ width: `${Math.max(2, share * 100)}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-zinc-500 tabular-nums dark:text-zinc-400">{pctFmt.format(share)}</span>
                  </div>
                </td>
                <td className={cn(td, "align-top")}>{formatInt(r.calls)}</td>
                <td className={cn(td, "align-top", r.failed > 0 ? "text-amber-700 dark:text-amber-300" : "text-zinc-400 dark:text-zinc-500")}>
                  {formatInt(r.failed)}
                </td>
                <td className={cn(td, "align-top text-zinc-600 dark:text-zinc-300")}>
                  {formatCompact(r.input_tokens)} / {formatCompact(r.output_tokens)}
                </td>
                <td className={cn(td, "align-top")}>{formatUSD(r.cost_usd)}</td>
                <td className={cn(td, "pr-5 align-top text-zinc-600 dark:text-zinc-300")}>
                  {formatMs(r.avg_latency_ms)} / {formatMs(r.p95_latency_ms)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- Stati -------------------------------------------------------------------

function LoadingState() {
  return (
    <div className="space-y-4" aria-label="Caricamento metriche">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Card key={i} className="space-y-2 p-4">
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-3 w-24" />
          </Card>
        ))}
      </div>
      <Card className="space-y-3 p-5">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3 p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-40 w-full" />
        </Card>
        <Card className="space-y-3 p-5">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-2/3" />
        </Card>
      </div>
    </div>
  );
}

function UnavailableState({ reason, onRetry, loading }: { reason: string; onRetry: () => void; loading: boolean }) {
  return (
    <Card className="mx-auto flex max-w-xl flex-col items-center px-6 py-12 text-center">
      <span className="relative flex size-16 items-center justify-center rounded-2xl bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
        <ServerOff className="size-8" aria-hidden />
        <span className="absolute -top-1.5 -right-1.5 size-4 rounded-full bg-amber-400/70" aria-hidden />
      </span>
      <h2 className="mt-5 text-lg font-semibold">Langfuse non è raggiungibile</h2>
      <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
        Le metriche di tracing non sono disponibili in questo momento. La chat e le prenotazioni funzionano
        normalmente: il tracing è solo osservazione.
      </p>
      <p className="mt-3 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-600 ring-1 ring-zinc-200 ring-inset dark:bg-zinc-950/40 dark:text-zinc-400 dark:ring-zinc-800">
        Motivo: {reason}
      </p>
      <div className="mt-5 w-full rounded-xl border border-zinc-200 bg-zinc-50/80 p-4 text-left text-sm dark:border-zinc-800 dark:bg-zinc-950/40">
        <p className="flex items-center gap-1.5 font-medium">
          <Terminal className="size-4 text-zinc-500 dark:text-zinc-400" aria-hidden />
          Come avviarlo
        </p>
        <p className="mt-1 text-zinc-600 dark:text-zinc-400">
          Dalla cartella del progetto avvia tutti i servizi, Langfuse compreso:
        </p>
        <code className="mt-2 block rounded-lg bg-zinc-900 px-3 py-2 font-mono text-xs text-zinc-100 dark:bg-black/60">
          docker compose up
        </code>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Al primo avvio Langfuse impiega circa un minuto a essere pronto su {LANGFUSE_URL}.
        </p>
      </div>
      <Button
        variant="secondary"
        className="mt-6"
        loading={loading}
        icon={<RotateCcw className="size-4" aria-hidden />}
        onClick={onRetry}
      >
        Riprova
      </Button>
    </Card>
  );
}

function Dashboard({ data }: { data: TracingSummaryAvailable }) {
  const t = data.totals;
  const maxTaskCalls = Math.max(1, ...data.by_task.map((r) => r.calls));
  const tasks = [...data.by_task].sort((a, b) => b.calls - a.calls);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Kpi icon={MessagesSquare} label="Turni" value={formatInt(t.turns)} sub="messaggi e azioni" />
        <Kpi icon={Sparkles} label="Chiamate LLM" value={formatInt(t.llm_calls)} sub={t.turns > 0 ? `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1 }).format(t.llm_calls / t.turns)} per turno` : "—"} />
        <Kpi
          icon={RotateCcw}
          label="Tentativi falliti"
          value={formatInt(t.failed_attempts)}
          sub={`${pctFmt.format(t.failure_rate)} · fallback/retry`}
          tone={t.failed_attempts > 0 ? "warn" : "neutral"}
        />
        <Kpi
          icon={Hash}
          label="Token"
          value={formatCompact(t.input_tokens + t.output_tokens)}
          sub={`in ${formatCompact(t.input_tokens)} · out ${formatCompact(t.output_tokens)}`}
        />
        <Kpi icon={Coins} label="Costo stimato" value={formatUSD(t.cost_usd)} sub="stima a listino" />
        <Kpi icon={Clock} label="Latenza turno" value={formatMs(t.avg_turn_latency_ms)} sub={`media · p95 ${formatMs(t.p95_turn_latency_ms)}`} />
      </div>

      <SectionCard icon={Cpu} title="Per provider e modello" subtitle="La barra mostra la quota di chiamate di ogni modello">
        <ModelTable rows={data.by_model} />
      </SectionCard>

      <div className="grid items-start gap-4 lg:grid-cols-5">
        <SectionCard icon={BarChart3} title="Costo nel tempo" subtitle="Costo stimato in USD per intervallo" className="lg:col-span-3">
          <CostChart series={data.series} />
        </SectionCard>

        <SectionCard icon={ListTree} title="Per task" subtitle="Chiamate LLM per compito" className="lg:col-span-2">
          {tasks.length === 0 ? (
            <EmptyNote>Nessun task nel periodo.</EmptyNote>
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {tasks.map((r) => (
                <li key={r.task} className="px-5 py-2.5">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate font-medium" title={r.task}>
                      {taskLabel(r.task)}
                    </span>
                    <span className="shrink-0 text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                      {formatInt(r.calls)} · {formatUSD(r.cost_usd)} · {formatMs(r.avg_latency_ms)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800" aria-hidden>
                    <div
                      className="h-full rounded-full bg-indigo-400 dark:bg-indigo-400"
                      style={{ width: `${Math.max(2, (r.calls / maxTaskCalls) * 100)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard icon={Activity} title="Turni recenti" subtitle="Ogni turno è una trace in Langfuse">
        {data.recent_turns.length === 0 ? (
          <EmptyNote>Nessun turno nel periodo: scrivi all'assistente per generare le prime trace.</EmptyNote>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {data.recent_turns.map((r, i) => {
              const level = r.level.toUpperCase();
              return (
                <li key={`${r.started_at}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2.5 text-sm">
                  <span className="min-w-0 flex-1 truncate font-medium">{TURN_LABELS[r.name] ?? r.name}</span>
                  <time dateTime={r.started_at} title={formatDateTime(r.started_at)} className="text-xs text-zinc-500 dark:text-zinc-400">
                    {formatRelative(r.started_at)}
                  </time>
                  <span className="w-16 text-right text-xs text-zinc-600 tabular-nums dark:text-zinc-300">{formatMs(r.latency_ms)}</span>
                  <Badge tone={LEVEL_TONE[level] ?? "neutral"} className="text-[11px]">
                    {LEVEL_LABELS[level] ?? r.level.toLowerCase()}
                  </Badge>
                  {r.trace_url ? (
                    <ExternalA
                      href={r.trace_url}
                      label="Apri la trace in Langfuse"
                      className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-300 dark:hover:text-indigo-200"
                    >
                      Apri trace
                      <ExternalLink className="size-3" aria-hidden />
                    </ExternalA>
                  ) : (
                    <span className="w-[4.75rem]" aria-hidden />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </SectionCard>

      {data.note && <p className="px-1 text-xs text-zinc-500 dark:text-zinc-400">* {data.note}</p>}
    </div>
  );
}

// --- Pagina ------------------------------------------------------------------

export function TracingPage() {
  const [period, setPeriod] = useState<TracingPeriod>("7d");
  const [summary, setSummary] = useState<TracingSummary | null>(null);
  const [loadedPeriod, setLoadedPeriod] = useState<TracingPeriod | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const reqId = useRef(0);

  const load = useCallback(async (p: TracingPeriod) => {
    const id = ++reqId.current;
    setLoading(true);
    try {
      const data = await getTracingSummary(p);
      if (id !== reqId.current) return; // risposta superata da una richiesta più recente
      setSummary(data);
      setLoadedPeriod(p);
      setError(null);
      setUpdatedAt(new Date().toISOString());
    } catch (err) {
      if (id === reqId.current) setError(errorMessage(err));
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(period);
  }, [period, load]);

  // Aggiornamento automatico ogni 30 s, solo con la scheda visibile.
  useEffect(() => {
    let timer: number | undefined;
    const start = () => {
      window.clearInterval(timer);
      timer = window.setInterval(() => void load(period), REFRESH_MS);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void load(period);
        start();
      } else {
        window.clearInterval(timer);
      }
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [period, load]);

  // Skeleton al primo caricamento e al cambio di periodo; il refresh periodico non svuota la vista.
  const showSkeleton = (summary === null || loadedPeriod !== period) && !error;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Activity className="size-6 text-indigo-600 dark:text-indigo-300" aria-hidden />
              Tracing
            </h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Metriche delle chiamate LLM delle <strong className="font-semibold text-zinc-800 dark:text-zinc-200">tue</strong>{" "}
              conversazioni: provider, token, costi stimati, latenze e fallback. I dati sono letti da Langfuse
              self-hosted, dove ogni turno è una trace consultabile.
            </p>
          </div>
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <ExternalA
              href={LANGFUSE_URL}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 text-sm font-medium text-zinc-800 shadow-xs hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              Apri Langfuse
              <ExternalLink className="size-4" aria-hidden />
            </ExternalA>
            <span className="inline-flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
              <KeyRound className="size-3" aria-hidden />
              locale: <span className="font-mono">admin@travel.local</span> / <span className="font-mono">travel-langfuse</span>
            </span>
          </div>
        </header>

        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div
            role="radiogroup"
            aria-label="Periodo"
            className="inline-flex rounded-xl bg-zinc-100 p-1 ring-1 ring-zinc-200 ring-inset dark:bg-zinc-800/60 dark:ring-zinc-700"
          >
            {PERIODS.map((p) => {
              const selected = p.value === period;
              return (
                <button
                  key={p.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setPeriod(p.value)}
                  className={cn(
                    "h-8 rounded-lg px-3 text-sm font-medium transition-colors",
                    selected
                      ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-900 dark:text-zinc-100"
                      : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
                  )}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            {updatedAt && (
              <span className="text-xs text-zinc-500 dark:text-zinc-400" aria-live="polite">
                Aggiornato alle {formatClock(updatedAt)} · ogni 30 s
              </span>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void load(period)}
              disabled={loading}
              icon={<RefreshCw className={cn("size-3.5", loading && "animate-spin")} aria-hidden />}
            >
              Aggiorna
            </Button>
          </div>
        </div>

        {error && (
          <Alert className="mb-4" onDismiss={() => setError(null)}>
            Impossibile caricare le metriche: {error}
          </Alert>
        )}

        {showSkeleton ? (
          <LoadingState />
        ) : summary === null ? null : summary.available ? (
          <Dashboard data={summary} />
        ) : (
          <UnavailableState reason={summary.reason} loading={loading} onRetry={() => void load(period)} />
        )}
      </div>
    </div>
  );
}
