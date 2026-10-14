# Assistente virtuale per viaggi personalizzati

Assistente conversazionale che raccoglie le esigenze dell'utente in chat (budget, destinazione, preferenze, periodo), costruisce itinerari completi (volo A/R, hotel per ogni notte, un'attività per ogni giorno) nel rispetto di budget e disponibilità, e li fa prenotare tramite chat.

Il principio che guida l'architettura:

> **L'LLM capisce e spiega, il codice decide e garantisce.**

L'LLM interpreta il linguaggio naturale e spiega i risultati. Prezzi, disponibilità, costruzione degli itinerari e prenotazioni sono responsabilità di codice deterministico e testato.

## Avvio rapido

Requisiti: Docker con Compose v2 e circa 4 GB di RAM liberi (lo stack completo, Langfuse incluso, ne usa circa 3,7 GB). Il primo avvio scarica le immagini e il modello di embedding, quindi richiede qualche minuto in più.

```bash
cd project
cp .env.example .env     # opzionale: serve solo per aggiungere chiavi Groq/Gemini
docker compose up --build
```

| Servizio | URL | Credenziali |
|---|---|---|
| Applicazione | <http://localhost:3000> | `demo` / `demo` oppure `reviewer` / `reviewer` |
| API (OpenAPI) | <http://localhost:8000/docs> | |
| Keycloak | <http://localhost:8080> | `admin` / `admin` |
| Langfuse (tracing) | <http://localhost:3001> | `admin@travel.local` / `travel-langfuse` |

Ci si può anche registrare dalla pagina di login. Le credenziali qui sopra, come le chiavi Langfuse `pk-lf-travel-local` / `sk-lf-travel-local` nel compose, valgono solo in locale.

Al primo avvio il backend applica le migrazioni, genera il catalogo sintetico, indicizza le attività nel database vettoriale e precarica le chat di esempio. **Non serve nessuna chiave API**: senza chiavi risponde il provider mock deterministico. Per usare gli LLM reali inserisci in `project/.env` almeno una chiave (Groq e/o Google AI Studio, entrambi con free tier): la catena è Groq → Gemini → Mock, i provider senza chiave vengono saltati e il mock resta l'ultimo anello. Ogni risposta in chat mostra il tag del provider che l'ha generata (`GROQ`, `GEMINI`, `MOCK`, `SYSTEM`).

### Chat precaricate

Gli utenti `demo` e `reviewer` trovano già quattro conversazioni, generate dall'orchestratore reale con il provider mock (per questo hanno il tag `MOCK` e sono identiche su ogni macchina):

| Conversazione | Cosa mostra |
|---|---|
| Consigliami tu · giugno | La meta la sceglie l'assistente, solo tra i paesi che rientrano nel budget |
| Giappone con 300 € · caso infattibile | Vincoli bloccanti e rilassamenti concreti proposti dal planner |
| Barcellona a maggio · prenotata | Variante scelta e prenotata, visibile nella dashboard prenotazioni |
| Grecia ad agosto · proposte e modifica | Tre varianti, sostituzione di un'attività, domanda fuori scope rifiutata |

Le chat vengono create una sola volta per utente: quelle eliminate non ricompaiono al riavvio. Per ripartire da zero: `docker compose down -v`.

### Tracing

Ogni turno di conversazione è una trace su Langfuse self-hosted ([ADR-0010](docs/adr/0010-osservabilita-langfuse-self-hosted.md)), con una generation per ogni tentativo verso un provider (i fallback sono visibili) e span per planner, RAG, tool e guardrail. Il costo è stimato sui prezzi di listino dei modelli: con i free tier non si paga nulla, ma la stima dice quanto costerebbe in produzione; per un modello senza prezzo noto il costo non viene stimato.

- La pagina **Tracing** dell'app mostra le metriche dell'utente corrente (turni, chiamate LLM, tentativi falliti, token, costo stimato, latenza media e p95, dettaglio per provider e modello, turni recenti). Le legge tramite il backend, così le chiavi Langfuse non arrivano mai al browser.
- Ogni risposta dell'assistente in chat ha un link **Trace** che apre la sua trace su Langfuse.
- Il tracing è best effort: se Langfuse non risponde l'app funziona lo stesso e la pagina mostra «non disponibile».

## Esempio di conversazione

> Siamo in due, budget 2500 euro, vorremmo andare in Grecia ad agosto per 5-7 giorni, partenza da Napoli. Ci piace il mare e la vita notturna.

L'assistente propone fino a 3 varianti (economica, bilanciata, premium). La variante si sceglie in chat o con il pulsante sulla card, e la prenotazione parte **solo** con il pulsante «Conferma e prenota». Altri casi da provare:

- «consigliami tu»: l'assistente sceglie la meta, ma solo tra quelle che rientrano nel budget;
- «ovunque»: il planner valuta tutte le destinazioni;
- budget troppo basso: l'assistente propone alternative concrete (meno giorni, altro mese, altra meta, budget minimo).

## Stato del progetto

Il progetto è costruito per fasi ([ADR-0015](docs/adr/0015-perimetro-priorita-esclusioni.md)); l'avanzamento dettagliato e le decisioni di implementazione sono in [`tracker.md`](tracker.md).

| Fase | Contenuto | Stato |
|---|---|---|
| 1 | Slice end-to-end con mock: dati, RAG, Keycloak, state machine, planner e validatore, prenotazione, UI | Fatta |
| 2 | LLM reali (Groq, Gemini) con fallback e cooldown, tool calling, streaming SSE | Fatta |
| 3 | Langfuse self-hosted, costi stimati, pagina Tracing | Fatta |
| 4 | Golden set, metriche, judge, CI | Da fare |
| 5 | Compaction dello storico | Da fare |
| 6 | Modifica delle prenotazioni | Da fare |

## Miglioramenti futuri

Ciò che non è stato fatto, con il piano previsto:

- **Eval e CI** ([ADR-0008](docs/adr/0008-valutazione-golden-set-judge.md)): golden set di conversazioni (casi semplici, ambigui, flessibili, infattibili, prompt injection, fuori scope e falsi rifiuti), metriche deterministiche (accuratezza dell'estrazione dei requisiti, validità dei vincoli, scelta del tool) per ogni provider con il mock come baseline, LLM-as-judge solo per tono e qualità delle spiegazioni; CI su GitHub Actions con ruff, pytest ed eval deterministici sul mock.
- **Compaction dello storico** ([ADR-0009](docs/adr/0009-storico-e-compaction.md)): oltre circa 8k token, riassunto dei messaggi vecchi più gli ultimi turni come contesto, senza mai riassumere lo stato strutturato. Storico persistito, elenco e ripresa delle conversazioni ci sono già; manca la ripresa con contesto compattato.
- **Modifica di una prenotazione esistente**: oggi si annulla (con ripristino dell'inventario) e si prenota di nuovo; la modifica richiederebbe la stessa verifica di disponibilità in un'unica transazione ([ADR-0006](docs/adr/0006-prenotazione-sicura.md)).
- **Costo per conversazione e per prenotazione** nella pagina Tracing ([ADR-0010](docs/adr/0010-osservabilita-langfuse-self-hosted.md)): oggi i costi sono aggregati per provider/modello, per task e nel tempo; manca il raggruppamento per sessione e il collegamento alla prenotazione.
- **`trace_id` nei log JSON** ([ADR-0017](docs/adr/0017-logging-strutturato.md)): il trace id è salvato sui messaggi e linkato dalla chat, ma non è ancora nel contesto dei log, che si correlano a Langfuse solo tramite `conversation_id`.

Le esclusioni volute (message broker, multimodale, solver ILP, login social, WebSocket, agente LLM libero, pagamenti, deploy cloud) restano tali: sono motivate in [ADR-0015](docs/adr/0015-perimetro-priorita-esclusioni.md), insieme alle condizioni che porterebbero a rivederle.

## Requisiti mancanti nella traccia e assunzioni

La traccia non specifica alcuni dati indispensabili. Sono gestiti in modo esplicito: **tutti i requisiti sono obbligatori** e l'assistente li chiede finché non li ha (nessun default silenzioso). Vedi [ADR-0002](docs/adr/0002-requisiti-strutturati-valori-flessibili.md).

| Dato | Come è gestito |
|---|---|
| Durata | Obbligatoria: un valore fisso o un intervallo (es. 5-7 giorni) |
| Aeroporto di partenza | Obbligatorio: Roma Fiumicino, Milano Malpensa o Napoli |
| Numero di viaggiatori | Obbligatorio, da 1 a 9 |
| Date precise | L'utente indica solo il mese; la data di partenza la sceglie il planner |

Assunzioni sul modello dei costi:

- "N giorni" corrispondono a N-1 notti, con un'attività per ciascuno degli N giorni;
- voli e attività hanno prezzo a persona, gli hotel a camera per notte;
- una camera ospita 2 persone;
- il budget è totale per tutto il gruppo;
- i prezzi sono interi in euro, così l'aritmetica del budget è esatta;
- il viaggio si svolge interamente nel mese indicato quando possibile, altrimenti inizia nel mese e finisce nel successivo;
- il catalogo copre i 12 mesi successivi a quello in cui viene generato, e un mese si riferisce sempre alla sua prossima occorrenza.

## Architettura

```text
frontend (React) ──► backend (FastAPI) ──► PostgreSQL   catalogo, inventario, itinerari, prenotazioni
        │                 │      └───────► Chroma       RAG sulle attività (embedding locali multilingue)
        │                 ├──────────────► Gateway LLM  Groq → Gemini → Mock
        │                 └──────────────► Langfuse     trace, generation, costi stimati (best effort)
        └──► Keycloak (OIDC)  login e registrazione; il backend valida solo i JWT
```

Componenti principali del backend (`project/src/backend/app/`):

| Modulo | Responsabilità |
|---|---|
| `domain/requirements.py` | `TripRequirements`: requisiti strutturati, valori flessibili, validazione sul catalogo |
| `domain/phases.py` | State machine delle fasi della conversazione |
| `domain/planner.py` | Planner greedy dietro l'interfaccia `Planner`, 3 varianti |
| `domain/validator.py` | Validatore deterministico, indipendente dal planner |
| `services/conversation.py` | Orchestratore: decide transizioni, destinazioni fattibili, cosa arriva all'utente |
| `services/booking.py` | Prenotazione: transazione, decremento condizionale, idempotenza, snapshot prezzi |
| `llm/` | Astrazione per task, gateway con fallback e cooldown, Interprete, provider mock |
| `rag/retriever.py` | Chroma con filtro obbligatorio su paese e mese, fallback a parole chiave |
| `observability.py` | Trace e span su Langfuse, no-op se Langfuse non è raggiungibile |
| `llm/prices.py`, `services/tracing_metrics.py` | Prezzi di listino per il costo stimato, metriche per la pagina Tracing |
| `seed/` | Catalogo deterministico e chat di esempio per gli utenti di prova |

Documentazione:

- [Sfide ingegneristiche e decisioni](docs/engineering-challenges.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Workflow di prenotazione (diagrammi)](docs/workflow-prenotazione.md)
- [Come ho usato l'AI generativa](docs/ai-usage.md)

## Struttura del repository

```text
├── README.md, tracker.md, CLAUDE.md
├── docs/                  sfide e decisioni, ADR, workflow di prenotazione, uso dell'AI
└── project/               tutto ciò che si esegue
    ├── docker-compose.yml
    ├── .env.example
    ├── infra/             realm Keycloak con utenti di prova, init di PostgreSQL (database app, Keycloak, Langfuse)
    └── src/
        ├── backend/       FastAPI: app/, migrations/, tests/
        └── frontend/      React + Vite
```

## Log

Il backend scrive log strutturati in JSON su stdout ([ADR-0017](docs/adr/0017-logging-strutturato.md)). Gli eventi hanno nomi stabili e non contengono mai il testo dei messaggi.

```bash
cd project
docker compose logs -f backend                         # tutti gli eventi
docker compose logs backend | grep '"booking.'         # solo le prenotazioni
```

## Sviluppo locale

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
cd project/src/backend
uv sync
uv run pytest            # unit e integration test su PostgreSQL (container usa-e-getta) + provider mock
uv run ruff check .
```

Frontend (Node 22):

```bash
cd project/src/frontend
npm install
npm run dev              # http://localhost:5173, /api proxato su localhost:8000
npm run build
```

I test usano PostgreSQL come l'applicazione: [testcontainers](https://testcontainers.com/) avvia un container usa-e-getta (serve Docker attivo), lo schema viene creato con le migrazioni Alembic reali e ogni test lavora su una copia pulita del catalogo, clonata da un database template. In CI si può puntare a un Postgres esistente con `TEST_DATABASE_URL`.
