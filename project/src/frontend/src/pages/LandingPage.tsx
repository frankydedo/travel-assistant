import { useState } from "react";
import {
  Calculator,
  Compass,
  LogIn,
  MessageSquare,
  Plane,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { login, register } from "../auth/keycloak";
import { HeroIllustration } from "../components/landing/HeroIllustration";
import { DESTINATIONS } from "../components/landing/destinations";
import { ThemeToggle } from "../components/ThemeToggle";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { cn } from "../components/ui/cn";

const FEATURES: { icon: LucideIcon; title: string; text: string; tile: string }[] = [
  {
    icon: MessageSquare,
    title: "Conversazione naturale",
    text: "Scrivi come parleresti a un'agenzia: budget, meta, periodo e cosa ti piace fare. L'assistente chiede solo quello che manca.",
    tile: "from-indigo-500 to-violet-600 shadow-indigo-500/30",
  },
  {
    icon: Wallet,
    title: "Itinerari nel tuo budget",
    text: "Volo di andata e ritorno, un hotel per ogni notte e un'attività per ogni giorno. Prezzi e disponibilità sono verificati dal sistema, non inventati dall'AI.",
    tile: "from-sky-500 to-indigo-600 shadow-sky-500/30",
  },
  {
    icon: ShieldCheck,
    title: "Prenoti con un clic",
    text: "Scegli la variante che preferisci tra economica, bilanciata e premium. La prenotazione parte solo con la tua conferma.",
    tile: "from-emerald-500 to-teal-600 shadow-emerald-500/30",
  },
];

const GLASS =
  "border border-white/70 bg-white/70 shadow-sm backdrop-blur-md dark:border-white/10 dark:bg-zinc-900/60";

function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-linear-to-b from-orange-50 via-rose-50 to-sky-50 dark:from-zinc-950 dark:via-[#16102e] dark:to-zinc-950" />
      <div className="absolute -top-40 -right-32 size-[36rem] rounded-full bg-orange-300/40 blur-3xl dark:bg-orange-500/15" />
      <div className="absolute top-1/3 -left-48 size-[34rem] rounded-full bg-sky-300/40 blur-3xl dark:bg-cyan-500/10" />
      <div className="absolute -bottom-40 left-1/3 size-[30rem] rounded-full bg-rose-300/30 blur-3xl dark:bg-violet-600/20" />
      <div className="absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)] bg-[radial-gradient(var(--color-zinc-900)_1px,transparent_1px)] [background-size:22px_22px] opacity-[0.06] dark:bg-[radial-gradient(white_1px,transparent_1px)] dark:opacity-[0.07]" />
    </div>
  );
}

function ChatPreview() {
  return (
    <>
      <div className="absolute top-[64%] left-0 hidden max-w-[15rem] motion-safe:animate-float sm:block lg:-left-4 xl:-left-10">
        <div className="rounded-2xl rounded-tr-md bg-indigo-600 px-4 py-2.5 text-sm leading-snug text-white shadow-lg shadow-indigo-600/25 dark:bg-indigo-500">
          Una settimana in Giappone a ottobre, budget 2.500 €
        </div>
      </div>
      <div
        className={cn("absolute right-0 -bottom-4 hidden w-[16.5rem] rounded-2xl p-3.5 motion-safe:animate-float sm:block lg:-right-4 xl:-right-8", GLASS)}
        style={{ animationDelay: "-3.5s" }}
      >
        <span className="inline-flex items-center gap-1 rounded-full bg-linear-to-r from-violet-50 to-indigo-50 px-2 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-violet-200 ring-inset dark:from-violet-500/15 dark:to-indigo-500/15 dark:text-violet-200 dark:ring-violet-400/30">
          <Sparkles className="size-3" aria-hidden />
          Generato con AI
        </span>
        <p className="mt-2 text-sm font-medium text-zinc-800 dark:text-zinc-100">Ho trovato 3 itinerari entro il budget</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {[
            ["Economica", "bg-emerald-500"],
            ["Bilanciata", "bg-sky-500"],
            ["Premium", "bg-amber-500"],
          ].map(([label, dot]) => (
            <span
              key={label}
              className="inline-flex items-center gap-1.5 rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            >
              <span className={cn("size-1.5 rounded-full", dot)} aria-hidden />
              {label}
            </span>
          ))}
        </div>
        <p className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
          <Calculator className="size-3" aria-hidden />
          Prezzi verificati dal sistema
        </p>
      </div>
    </>
  );
}

export function LandingPage({ authUnavailable = false }: { authUnavailable?: boolean }) {
  const [busy, setBusy] = useState<"login" | "register" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(kind: "login" | "register") {
    setBusy(kind);
    setError(null);
    try {
      // Redirect a Keycloak: in caso di successo la pagina viene abbandonata.
      await (kind === "login" ? login() : register());
    } catch {
      setError("Impossibile aprire la pagina di accesso. Verifica che Keycloak sia avviato e riprova.");
      setBusy(null);
    }
  }

  return (
    <div className="relative isolate flex min-h-full flex-col overflow-hidden text-zinc-900 dark:text-zinc-100">
      <Backdrop />

      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <span className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-500/30">
            <Plane className="size-4 -rotate-12" aria-hidden />
          </span>
          <span className="hidden text-sm font-semibold tracking-tight min-[380px]:inline">Assistente viaggi</span>
        </span>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void go("login")}
            disabled={busy !== null}
            icon={<LogIn className="size-4" aria-hidden />}
          >
            Accedi
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6">
        <section className="grid items-center gap-10 pt-6 pb-10 lg:grid-cols-[1.05fr_1fr] lg:gap-6 lg:pt-14 lg:pb-16">
          <div className="text-center lg:text-left">
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-zinc-700 dark:text-zinc-300", GLASS)}>
              <Compass className="size-3.5 text-indigo-600 dark:text-indigo-300" aria-hidden />
              Assistente di viaggio conversazionale
            </span>
            <h1 className="mt-5 text-4xl leading-[1.08] font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl">
              Il tuo prossimo viaggio,{" "}
              <span className="bg-linear-to-r from-orange-600 via-rose-600 to-violet-700 bg-clip-text text-transparent dark:from-amber-300 dark:via-rose-300 dark:to-violet-300">
                organizzato in una conversazione
              </span>
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-pretty text-zinc-700 sm:text-lg lg:mx-0 dark:text-zinc-300">
              Racconta budget, destinazione, attività preferite e periodo. Ricevi un itinerario completo, con volo di
              andata e ritorno, un hotel per ogni notte e un'attività per ogni giorno, e prenotalo direttamente in chat.
            </p>

            {(authUnavailable || error) && (
              <Alert className="mx-auto mt-6 max-w-xl text-left lg:mx-0">
                {error ?? "Il servizio di accesso non risponde al momento. Puoi comunque provare ad accedere: se il problema persiste verifica che Keycloak sia avviato."}
              </Alert>
            )}

            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row lg:justify-start">
              <Button
                size="lg"
                onClick={() => void go("login")}
                loading={busy === "login"}
                disabled={busy !== null}
                icon={<LogIn className="size-5" aria-hidden />}
                className="shadow-lg shadow-indigo-600/25"
              >
                Accedi con SSO
              </Button>
              <Button
                size="lg"
                variant="secondary"
                onClick={() => void go("register")}
                loading={busy === "register"}
                disabled={busy !== null}
                icon={<UserPlus className="size-5" aria-hidden />}
              >
                Crea un account
              </Button>
            </div>

            <p className="mt-6 inline-flex items-center gap-2 text-left text-[13px] text-zinc-600 sm:text-sm dark:text-zinc-400">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-violet-100 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300">
                <Sparkles className="size-3.5" aria-hidden />
              </span>
              I contenuti generati con AI sono sempre segnalati
            </p>
          </div>

          <div className="relative mx-auto w-full max-w-md sm:max-w-lg lg:max-w-none">
            <HeroIllustration className="h-auto w-full" />
            <ChatPreview />
          </div>
        </section>

        <section aria-labelledby="lp-destinations" className="pb-12">
          <h2
            id="lp-destinations"
            className="text-center text-xs font-semibold tracking-wider text-zinc-500 uppercase lg:text-left dark:text-zinc-400"
          >
            Destinazioni in catalogo
          </h2>
          <ul className="mt-3 flex flex-wrap justify-center gap-2 lg:justify-start">
            {DESTINATIONS.map((d) => (
              <li key={d.city} className={cn("inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm", GLASS)}>
                <span className={cn("size-2.5 rounded-full ring-2 ring-white dark:ring-zinc-900", d.dot)} aria-hidden />
                <span className="font-medium">{d.city}</span>
                <span className="text-zinc-500 dark:text-zinc-400">{d.country}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Caratteristiche" className="grid gap-4 pb-16 md:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text, tile }) => (
            <article key={title} className={cn("rounded-2xl p-5", GLASS)}>
              <span className={cn("flex size-10 items-center justify-center rounded-xl bg-linear-to-br text-white shadow-md", tile)}>
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{text}</p>
            </article>
          ))}
        </section>
      </main>

      <footer className="border-t border-zinc-900/5 dark:border-white/10">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-4 py-5 text-xs text-zinc-500 sm:flex-row sm:px-6 dark:text-zinc-400">
          <p>Assistente viaggi · prototipo dimostrativo con dati sintetici, nessun pagamento reale</p>
          <p className="inline-flex items-center gap-1.5">
            <ShieldCheck className="size-3.5" aria-hidden />
            Accesso tramite Keycloak (OpenID Connect)
          </p>
        </div>
      </footer>
    </div>
  );
}
