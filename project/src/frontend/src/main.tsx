import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Plane } from "lucide-react";
import { App } from "./App";
import { initKeycloak } from "./auth/keycloak";
import { LandingPage } from "./pages/LandingPage";
import "./theme/theme";
import "./styles.css";

const rootEl = document.getElementById("root")!;
const root = createRoot(rootEl);

type AuthState = "loading" | "anonymous" | "unavailable" | "authenticated";
let state: AuthState = "loading";

function render(next: AuthState) {
  state = next;
  if (next === "loading") {
    root.render(
      <div className="flex h-full items-center justify-center" role="status" aria-label="Caricamento">
        <span className="flex size-10 items-center justify-center rounded-xl bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30 motion-safe:animate-pulse">
          <Plane className="size-5 -rotate-12" aria-hidden />
        </span>
      </div>,
    );
    return;
  }
  root.render(
    <StrictMode>
      {next === "authenticated" ? (
        <BrowserRouter>
          <App />
        </BrowserRouter>
      ) : (
        // Nessuna chiamata API dalla landing: l'utente non è autenticato.
        <LandingPage authUnavailable={next === "unavailable"} />
      )}
    </StrictMode>,
  );
}

render("loading");

// Keycloak va inizializzato una sola volta, fuori da React (StrictMode esegue gli effect due volte).
initKeycloak()
  .then((authenticated) => render(authenticated ? "authenticated" : "anonymous"))
  .catch(() => {
    // Keycloak non raggiungibile: si mostra comunque la landing, con un avviso.
    if (state !== "authenticated") render("unavailable");
  });

// Il check silenzioso di keycloak-js non ha un timeout proprio: se l'iframe non risponde
// non si resta bloccati sullo splash. Se poi la verifica riesce, si passa all'app.
window.setTimeout(() => {
  if (state === "loading") render("anonymous");
}, 8000);
