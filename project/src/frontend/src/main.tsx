import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { initKeycloak } from "./auth/keycloak";
import "./styles.css";

const rootEl = document.getElementById("root")!;
const root = createRoot(rootEl);

// Keycloak va inizializzato una sola volta, fuori da React (StrictMode esegue gli effect due volte).
initKeycloak()
  .then((authenticated) => {
    if (!authenticated) return; // login-required: keycloak-js ha già rediretto al login.
    root.render(
      <StrictMode>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </StrictMode>,
    );
  })
  .catch(() => {
    root.render(
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md rounded-2xl border border-rose-200 bg-white p-6 shadow-sm dark:border-rose-500/30 dark:bg-zinc-900">
          <h1 className="text-lg font-semibold">Autenticazione non disponibile</h1>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Impossibile contattare Keycloak. Verifica che il servizio sia avviato e ricarica la pagina.
          </p>
        </div>
      </div>,
    );
  });
