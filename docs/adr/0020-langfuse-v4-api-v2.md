# ADR-0020 — Langfuse v4 e API pubbliche v2 per la pagina Tracing

- **Stato:** Accettata (aggiorna [ADR-0010](0010-osservabilita-langfuse-self-hosted.md) su versione e API)

## Contesto

ADR-0010 prevedeva Langfuse v3 self-hosted. Al momento dell'implementazione l'immagine corrente è la v4, che gira in modalità *events_only*: gli endpoint pubblici storici (`/api/public/traces`, `/api/public/observations`) rispondono 404. La pagina Tracing li avrebbe usati per leggere le metriche.

## Decisione

- Nel compose si usa **Langfuse v4** (`langfuse-web` e `langfuse-worker`), con lo stesso schema di ADR-0010: ClickHouse, Redis, MinIO e il PostgreSQL condiviso (database `langfuse`), con inizializzazione headless di organizzazione, progetto, utente e chiavi.
- Il backend legge gli aggregati dalla **Metrics API v2** (`/api/public/v2/metrics`) e gli ultimi turni dalla **Observations API v2** (`/api/public/v2/observations`), sempre filtrati sull'utente del JWT.
- La pagina Tracing mostra costi per provider/modello, per task e nel tempo. Il costo per singola prenotazione previsto da ADR-0010 resta un miglioramento futuro.

## Motivazione

Restare sulla v3 avrebbe significato fissare un'immagine non più corrente solo per usare endpoint dismessi. Le API v2 sono quelle supportate dalla v4 e permettono già le aggregazioni che servono (somme, medie, p95, serie temporali) senza scaricare le singole osservazioni.

## Conseguenze

- **Positive:** versione corrente, aggregazioni calcolate da Langfuse, nessuna chiave nel browser.
- **Negative:** il compose completo richiede circa 3,7 GB di RAM (misurati); le API v2 sono più recenti e il loro formato va verificato a ogni aggiornamento di Langfuse.
