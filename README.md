# Assistente virtuale per viaggi personalizzati

Assistente conversazionale che raccoglie le esigenze dell'utente in chat (budget, destinazione, preferenze, periodo), costruisce itinerari completi (volo A/R, hotel per ogni notte, un'attività per ogni giorno) nel rispetto di budget e disponibilità, e li fa prenotare tramite chat.

Il principio che guida l'architettura:

> **L'LLM capisce e spiega, il codice decide e garantisce.**

L'LLM interpreta il linguaggio naturale e spiega i risultati. Prezzi, disponibilità, costruzione degli itinerari e prenotazioni sono responsabilità di codice deterministico e testato.

## Avvio rapido

Requisiti: Docker con Compose v2 e circa 4 GB di RAM liberi.

```bash
cd project
docker compose up --build
```

| Servizio | URL |
|---|---|
| Applicazione | http://localhost:3000 |
| API (OpenAPI) | http://localhost:8000/docs |
| Keycloak (admin / admin) | http://localhost:8080 |

Utenti di prova: `demo` / `demo` e `reviewer` / `reviewer`. In alternativa ci si può registrare dalla pagina di login.

Al primo avvio il backend applica le migrazioni, genera il catalogo sintetico e indicizza le attività nel database vettoriale. **Non serve nessuna chiave API**: senza chiavi risponde il provider mock deterministico, e ogni risposta in chat mostra il tag del provider che l'ha generata.

## Esempio di conversazione

> Siamo in due, budget 2500 euro, vorremmo andare in Grecia ad agosto per 5-7 giorni, partenza da Napoli. Ci piace il mare e la vita notturna.

L'assistente propone fino a 3 varianti (economica, bilanciata, premium). La variante si sceglie in chat o con il pulsante sulla card, e la prenotazione parte **solo** con il pulsante «Conferma e prenota». Altri casi da provare:

- «consigliami tu»: l'assistente sceglie la meta, ma solo tra quelle che rientrano nel budget;
- «ovunque»: il planner valuta tutte le destinazioni;
- budget troppo basso: l'assistente propone alternative concrete (meno giorni, altro mese, altra meta, budget minimo).

## Stato del progetto

Il progetto è costruito per fasi (vedi [ADR-0015](docs/adr/0015-perimetro-priorita-esclusioni.md)), e l'avanzamento dettagliato è in [`tracker.md`](tracker.md). Ciò che non è implementato è dichiarato lì, insieme al motivo.

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
        │                 └──────────────► Gateway LLM  Gemini → Groq → LM Studio → Mock
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
    ├── infra/             realm Keycloak, init di PostgreSQL
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
