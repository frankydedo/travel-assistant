# ADR-0011 — Streaming delle risposte via SSE

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A11](../engineering-challenges.md#a11-latenza-e-ux--adr-0011)

## Contesto

Un turno di chat può durare diversi secondi: estrazione, planner, RAG, generazione della risposta ed eventuali fallback tra provider. Senza feedback progressivo l'utente vede uno schermo fermo.

## Opzioni considerate

- **Risposta unica** (request/response) con indicatore di caricamento.
- **Server-Sent Events (SSE).**
- **WebSocket.**

## Decisione

- **SSE** sull'endpoint del messaggio di chat, con eventi tipizzati:
  - `progress`, per lo stato di avanzamento ("cerco voli…", "cerco hotel…");
  - `token`, per il testo in streaming;
  - `itinerary`, con il JSON strutturato delle varianti;
  - `done`, con provider, modello e ID della trace;
  - `error`.
- Gli itinerari sono renderizzati come **card dal JSON strutturato**, non estratti dal testo dell'LLM.
- Lato client lo stream si legge con **`fetch` + `ReadableStream`**: l'`EventSource` nativo supporta solo GET e non permette di inviare l'header `Authorization` con il token OIDC.

## Motivazione

La comunicazione è unidirezionale: un turno è una richiesta del client seguita da uno stream del server. SSE copre esattamente questo, sopra HTTP normale, senza gestire connessioni persistenti. WebSocket aggiungerebbe bidirezionalità che non serve, più gestione di stato e riconnessioni.

## Conseguenze

- **Positive:** UX reattiva, infrastruttura HTTP standard, il fallback tra provider resta visibile come `progress`.
- **Negative:** il parsing dello stream lato client va scritto a mano (poche righe), oppure delegato a una libreria leggera.
