# ADR-0010 — Osservabilità con Langfuse self-hosted e pagina Tracing

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A10, §C2](../engineering-challenges.md#a10-osservabilità-e-costi--adr-0010)

## Contesto

In un sistema basato su LLM bisogna sapere, per ogni risposta, quale modello è stato chiamato, con quale prompt, quanti token ha consumato, quanto ha impiegato, se è scattato un fallback e quanto costerebbe. Il costo per conversazione è la metrica di business di un assistente AI.

Il vincolo è che il reviewer non ha account o chiavi di servizi esterni.

## Opzioni considerate

- **Langfuse Cloud:** leggero, ma richiede un account al reviewer.
- **Langfuse self-hosted:** funziona subito, ma porta circa 6 container.
- **Langfuse self-hosted in un profilo compose opzionale.**
- **Tabella `llm_calls` propria** con una dashboard fatta in casa.
- **Langtrace / Grafana.**

## Decisione

- **Langfuse v3 self-hosted** nel docker-compose principale, con organizzazione, progetto e chiavi API **pre-create all'avvio** (inizializzazione headless da variabili d'ambiente): il tracing funziona con `docker compose up`, senza account.
- **Strumentazione:**
  - ogni turno di chat è una **trace**, con utente, conversazione e fase;
  - ogni chiamata LLM (estrazione, risposta, compaction, judge) è una **generation** con provider, modello, token, latenza, esito, eventuali fallback e versione del prompt;
  - le chiamate al planner e al RAG sono span.
- **Costo stimato a listino:** i free tier costano 0€, quindi il backend calcola il costo da una tabella prezzi di riferimento per modello (configurabile) e lo invia con ogni generation. L'obiettivo è mostrare quanto costerebbe il sistema in produzione.
- **Pagina "Tracing" nella UI:**
  - le metriche vengono lette dall'API di Langfuse **tramite il backend**, così le chiavi restano lato server;
  - mostra chiamate e token per provider, latenza media e p95, tasso di fallback ed errori, costo stimato per conversazione e per prenotazione;
  - ogni messaggio in chat ha un link alla propria trace.

## Motivazione

- Langfuse è lo standard open source per il tracing LLM, e il self-hosting elimina la dipendenza dalle chiavi del reviewer.
- Una tabella propria duplicherebbe ciò che Langfuse fa meglio (trace annidate, dataset per gli eval, confronto tra versioni dei prompt).
- Grafana serve per metriche di sistema, non specifiche per LLM. Langtrace è meno diffuso e qui non porta vantaggi.
- La pagina in UI porta l'analisi dei costi dentro il prodotto, invece di lasciarla in uno strumento esterno.

## Conseguenze

- **Positive:** osservabilità completa senza configurazione, costi visibili, base per gli eval (ADR-0008).
- **Negative:**
  - circa 6 container in più (ClickHouse, Redis, MinIO, web, worker, più Postgres condiviso) e un uso di RAM sensibile, da dichiarare nel README;
  - l'ingestione di Langfuse è asincrona, quindi le metriche compaiono con qualche secondo di ritardo.
- **Mitigazione:** se Langfuse non è raggiungibile l'app continua a funzionare (il tracing è *best effort*) e la pagina Tracing mostra lo stato "non disponibile".
