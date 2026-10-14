# Frontend

React 18 + TypeScript (strict) + Vite. Autenticazione con Keycloak (OIDC, Authorization Code + PKCE) tramite `keycloak-js`. Stile con Tailwind CSS v4 (plugin `@tailwindcss/vite`, tema chiaro/scuro con un interruttore: dark mode a classe `.dark` su `<html>`, scelta salvata in localStorage e applicata da uno script inline in `index.html` per evitare il lampo del tema sbagliato; al primo accesso il valore iniziale viene dal sistema) e icone `lucide-react`. Nessuna libreria di componenti o di stato.

## Comandi

```bash
npm install
npm run dev      # dev server su http://localhost:5173, proxy /api -> http://localhost:8000
npm run build    # type-check (tsc --noEmit) + build di produzione in dist/
npm run lint     # solo type-check
npm run preview  # serve la build locale
```

In sviluppo servono Keycloak su `http://localhost:8080` (realm `travel`, client pubblico `travel-frontend` con redirect URI `http://localhost:5173/*`) e il backend su `http://localhost:8000`.

## Variabili d'ambiente

Lette a build time da Vite (vedi `.env.example`); se assenti valgono i default.

| Variabile | Default |
|---|---|
| `VITE_KEYCLOAK_URL` | `http://localhost:8080` |
| `VITE_KEYCLOAK_REALM` | `travel` |
| `VITE_KEYCLOAK_CLIENT_ID` | `travel-frontend` |

Le API sono sempre chiamate sul percorso relativo `/api`.

## Docker

`Dockerfile` multi-stage (build con `node:22-alpine`, runtime `nginx:alpine`). `nginx.conf` serve la SPA sulla porta 80 con fallback su `index.html` e inoltra `/api/` a `http://backend:8000` mantenendo il prefisso, con `proxy_buffering off` per lo streaming SSE. Il nome `backend` è risolto a ogni richiesta tramite il DNS di Docker (`resolver 127.0.0.11`), così un backend ricreato non lascia nginx sul vecchio IP (502). Le `VITE_*` si passano come build arg.

## Struttura

- `src/api/client.ts`: unico punto di accesso HTTP (token Bearer rinnovato prima di ogni chiamata). `sendMessageStream` legge lo streaming SSE con `fetch` + `ReadableStream` e ripiega su `sendMessage`, l'endpoint senza streaming.
- `src/api/types.ts`: tipi del contratto API.
- `src/auth/keycloak.ts`: inizializzazione Keycloak, token, logout.
- `src/pages/`: Chat (`/`), Prenotazioni (`/prenotazioni`), Tracing (`/tracing`, metriche Langfuse lette tramite il backend).
- `src/components/`: sidebar conversazioni, messaggi, card itinerario, callout di conferma, pannello stato/requisiti, composer, messaggio in streaming, rendering Markdown sicuro.
- `src/components/ui/`: primitive (Button, Badge, Card, Tooltip, Alert, Skeleton, Drawer, ConfirmDialog).
- `src/components/Provenance.tsx`: marcatori di provenienza. Sparkles = testo generato da AI (`ai_generated`, `description_ai_generated`); Cpu = provider di riserva deterministico (MOCK); ShieldCheck/Calculator = sistema e dati calcolati dal codice (prezzi, itinerari, conferma). Una legenda fissa è in fondo al pannello di stato.

Gli itinerari sono resi dal JSON strutturato restituito dal backend, mai dal testo dell'LLM. La prenotazione parte solo dal pulsante "Conferma e prenota", con una `Idempotency-Key` generata per tentativo e riusata se si riprova dopo un errore di rete o 5xx.
