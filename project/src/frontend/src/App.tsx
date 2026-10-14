import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { Activity, LogOut, MessagesSquare, Plane, Ticket, type LucideIcon } from "lucide-react";
import { getMe } from "./api/client";
import { logout, tokenDisplayName } from "./auth/keycloak";
import { UserAvatar } from "./components/Avatar";
import { Button } from "./components/ui/Button";
import { cn } from "./components/ui/cn";
import { CatalogProvider } from "./lib/catalog";
import { BookingsPage } from "./pages/BookingsPage";
import { ChatPage } from "./pages/ChatPage";
import { TracingPage } from "./pages/TracingPage";

const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", label: "Chat", icon: MessagesSquare, end: true },
  { to: "/prenotazioni", label: "Prenotazioni", icon: Ticket },
  { to: "/tracing", label: "Tracing", icon: Activity },
];

export function App() {
  const [userName, setUserName] = useState(tokenDisplayName());

  useEffect(() => {
    getMe()
      .then((me) => setUserName(me.name || me.username))
      .catch(() => {
        // Se /api/me non risponde si resta sul nome letto dal token.
      });
  }, []);

  return (
    <CatalogProvider>
      <div className="flex h-full flex-col">
        <header className="z-20 flex h-14 shrink-0 items-center gap-2 border-b border-zinc-200 bg-white/80 px-3 backdrop-blur sm:gap-4 sm:px-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          <NavLink to="/" className="flex shrink-0 items-center gap-2 rounded-lg" aria-label="Assistente viaggi, vai alla chat">
            <span className="flex size-8 items-center justify-center rounded-lg bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-500/30">
              <Plane className="size-4 -rotate-12" aria-hidden />
            </span>
            <span className="hidden text-sm font-semibold tracking-tight md:inline">Assistente viaggi</span>
          </NavLink>

          <nav aria-label="Sezioni" className="flex min-w-0 flex-1 justify-center md:justify-start">
            <div className="flex items-center gap-0.5 rounded-full bg-zinc-100 p-1 dark:bg-zinc-800/80">
              {NAV.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-medium transition-colors sm:px-3",
                      isActive
                        ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                        : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
                    )
                  }
                >
                  <Icon className="hidden size-3.5 sm:block" aria-hidden />
                  {label}
                </NavLink>
              ))}
            </div>
          </nav>

          <div className="flex shrink-0 items-center gap-2">
            <UserAvatar name={userName} />
            <span className="hidden max-w-40 truncate text-sm font-medium lg:inline">{userName}</span>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Esci" title="Esci">
              <LogOut className="size-4" aria-hidden />
            </Button>
          </div>
        </header>

        <main className="min-h-0 flex-1">
          <Routes>
            <Route path="/" element={<ChatPage userName={userName} />} />
            <Route path="/prenotazioni" element={<BookingsPage />} />
            <Route path="/tracing" element={<TracingPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </CatalogProvider>
  );
}
