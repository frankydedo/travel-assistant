# Assistente virtuale per viaggi personalizzati

Assistente conversazionale che raccoglie le esigenze dell'utente in chat (budget, destinazione, preferenze, periodo), costruisce itinerari completi (volo A/R, hotel per ogni notte, un'attività per ogni giorno) nel rispetto di budget e disponibilità, e li fa prenotare tramite chat.

Il principio che guida l'architettura:

> **L'LLM capisce e spiega, il codice decide e garantisce.**

L'LLM interpreta il linguaggio naturale e spiega i risultati. Prezzi, disponibilità, costruzione degli itinerari e prenotazioni sono responsabilità di codice deterministico e testato.

> **Branch `develop`:** contiene il lavoro nato provando l'app da utente con gli LLM reali (giorni di viaggio, tool sul catalogo, verifiche sul testo dell'LLM, chat precaricate registrate con i modelli veri). Cosa è cambiato rispetto a `main`, e perché: [docs/develop-rispetto-a-main.md](docs/develop-rispetto-a-main.md).

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
| Database (pgweb, sola lettura) | <http://localhost:8081> | nessun login |

Con pgweb si può controllare cosa garantisce il codice: `bookings` (snapshot del prezzo, chiave di idempotenza), `hotel_availability.rooms_left` e `activity_availability.spots_left` (scendono dopo una prenotazione e risalgono dopo un annullamento), `conversations.requirements` e il provider di ogni riga di `messages`. L'accesso è in sola lettura su due livelli, un ruolo PostgreSQL con il solo `SELECT` e la sessione read-only di pgweb, così i dati li modifica solo l'applicazione.

Ci si può anche registrare dalla pagina di login. Le credenziali qui sopra, come le chiavi Langfuse `pk-lf-travel-local` / `sk-lf-travel-local` nel compose, valgono solo in locale.

Al primo avvio il backend applica le migrazioni, genera il catalogo sintetico, indicizza le attività nel database vettoriale e precarica le chat di esempio. **Non serve nessuna chiave API**: senza chiavi risponde il provider mock deterministico. Per usare gli LLM reali inserisci in `project/.env` almeno una chiave (Groq e/o Google AI Studio, entrambi con free tier): la catena è Groq → Gemini → Mock, i provider senza chiave vengono saltati e il mock resta l'ultimo anello. Ogni risposta in chat mostra il tag del provider che l'ha generata (`GROQ`, `GEMINI`, `MOCK`, `SYSTEM`).

### Chat precaricate

Gli utenti `demo` e `reviewer` trovano sei conversazioni **registrate con gli LLM reali** (Groq e, quando Groq è al limite, Gemini, con i tag `GROQ` e `GEMINI`; i messaggi `SYSTEM` sono testi fissi scritti dal codice). Sono state fatte via API da un tester che si comportava come un utente, anche «difficile», e poi esportate in un fixture (`app/seed/fixtures/demo_conversations.json`). Il seed le ricarica così come sono, senza chiamare nessun LLM e senza chiavi: quello che si legge è ciò che hanno scritto davvero i modelli.

| Conversazione | Cosa mostra |
|---|---|
| Coppia indecisa · terme e buon cibo, consigliami tu · prenotata | Richiesta vaga raccolta in più turni, meta scelta dall'assistente tra quelle fattibili, domanda su un'attività con risposta ancorata al catalogo («nel catalogo non è indicato»), prenotazione con doppio invio registrata una volta sola |
| I soldi non sono un problema · ovunque, tre mete, poi un tetto di 1500 € | Valori «qualsiasi» ([ADR-0021](docs/adr/0021-valori-qualsiasi-espliciti.md)), tre paesi e aeroporti diversi ([ADR-0022](docs/adr/0022-varianti-con-budget-illimitato-e-ovunque.md)), cambio di budget a metà, sostituzione di un'attività indicata per nome |
| Giappone, voli notturni · «prenota tu», annullata e riprenotata | Giorni di viaggio per gli orari dei voli ([ADR-0023](docs/adr/0023-giorni-di-viaggio.md)), variante mancante spiegata, data esatta, «prenota tu» che porta solo alla selezione, annullamento che riapre la chat ([ADR-0024](docs/adr/0024-annullamento-riapre-la-conversazione.md)) e nuova prenotazione |
| Cliente difficile · injection, richieste impossibili, budget troppo basso | Prompt injection e fuori tema rifiutati con testi fissi, valori fuori catalogo spiegati dal codice, budget infattibile con costo minimo stimato, «non voglio la premium» che non seleziona nulla |
| Famiglia con bambini · Spagna a luglio, attività per famiglie | Pubblico di riferimento delle attività, una sostituzione sbagliata corretta dopo l'insistenza dell'utente, hotel migliore rifiutato perché fuori budget, variante in attesa di conferma |
| Curioso del catalogo · destinazioni, voli, hotel, poi l'Islanda | Domande sul catalogo con i tool di sola lettura ([ADR-0026](docs/adr/0026-tool-di-sola-lettura-sul-catalogo.md)): destinazioni, voli disponibili in un mese, hotel e attività invernali, poi le proposte; risposte di Gemini quando Groq è al limite di token |

Le trascrizioni contengono anche le risposte imperfette dei modelli: è voluto, e l'analisi è in [docs/conversazioni-reali.md](docs/conversazioni-reali.md).

- **Catalogo:** il catalogo è deterministico per mese di generazione, e le chat valgono per quello con cui sono state registrate (`catalog_start` nel fixture). Se il seed gira in un altro mese le chat restano leggibili come storico (le card sono istantanee salvate), ma le prenotazioni registrate non riprendono l'inventario e le proposte potrebbero non essere più modificabili.
- **Una volta per utente:** le chat vengono create solo per un utente nuovo, quindi quelle eliminate non ricompaiono al riavvio. Per ripartire da zero: `docker compose down -v`.
- **Registrarne di nuove:** dopo aver chattato come `reviewer`, `docker compose exec -T backend python -m app.seed.demo export > src/backend/app/seed/fixtures/demo_conversations.json` (da `project/`).

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

Emersi dalle conversazioni con gli LLM reali e dalle loro verifiche ([docs/conversazioni-reali.md](docs/conversazioni-reali.md)):

- **Affermazioni qualitative non supportate**: il controllo nel codice copre gli importi, non frasi come «relax sulla spiaggia» a novembre o «adatta ai bambini». Piano: confrontare categorie e pubblico citati con quelli dell'attività, e misurare il resto con le eval (judge).
- **Azioni dichiarate ma non fatte** («eliminiamo la variante Premium»): oggi solo una regola nel prompt. Piano: un controllo che segnali verbi d'azione nella risposta quando nessun tool è stato eseguito.
- **Fatti dei tool riformulati male**: per esempio un giorno di viaggio attribuito alla variante sbagliata, o l'aeroporto già scelto messo tra gli «altri». Piano: casi dedicati nel golden set e dati più espliciti nei risultati dei tool.
- **Orario delle attività**: il catalogo ha la durata ma non la fascia oraria, quindi una serata o la caccia all'aurora possono finire nel giorno del ritorno con un volo pomeridiano (ADR-0023). Piano: fascia oraria nel catalogo e nel controllo dei giorni di viaggio.
- **Peso del pubblico di riferimento**: con ±0,15 un'attività per coppie può ancora finire in un viaggio con bambini. Piano: tarare il peso sul golden set, oppure filtrare quando il pubblico è esplicito.
- **Scelte implicite da dichiarare sempre**: l'anno del mese richiesto (la prossima occorrenza può essere l'anno dopo) e le date diverse tra le varianti. In parte già passate alla risposta; piano: dirle sempre nelle proposte.
- **Dettagli e forma delle risposte**: descrizione dell'hotel nei dettagli di una variante; «quale preferisci?» con una sola alternativa; il modello sbaglia a volte i nomi («Terme di Segestane»).
- **Chat registrate e catalogo**: le chat precaricate valgono per il catalogo del mese in cui sono state registrate. Piano: fissare il mese del catalogo per la demo, oppure registrarle di nuovo con `python -m app.seed.demo export`.

Le esclusioni volute (message broker, multimodale, solver ILP, login social, WebSocket, agente LLM libero, pagamenti, deploy cloud) restano tali: sono motivate in [ADR-0015](docs/adr/0015-perimetro-priorita-esclusioni.md), insieme alle condizioni che porterebbero a rivederle.

## Requisiti mancanti nella traccia e assunzioni

La traccia non specifica alcuni dati indispensabili. Sono gestiti in modo esplicito: **tutti i requisiti sono obbligatori** e l'assistente li chiede finché non li ha (nessun default silenzioso). Vedi [ADR-0002](docs/adr/0002-requisiti-strutturati-valori-flessibili.md). Un valore «qualsiasi» è accettato solo se l'utente lo dice: il codice lo verifica sul suo messaggio, così l'LLM non può usarlo per riempire un dato mancante ([ADR-0021](docs/adr/0021-valori-qualsiasi-espliciti.md)).

| Dato | Come è gestito |
|---|---|
| Durata | Obbligatoria: un valore fisso o un intervallo (es. 5-7 giorni) |
| Budget | Obbligatorio: un importo totale, oppure «illimitato» se l'utente lo dice esplicitamente |
| Preferenze | Obbligatorie: una o più categorie, oppure «nessuna preferenza» detto esplicitamente |
| Aeroporto di partenza | Obbligatorio: Roma Fiumicino, Milano Malpensa, Napoli o «qualsiasi aeroporto» (il planner li confronta; il costo per raggiungere l'aeroporto non è considerato) |
| Numero di viaggiatori | Obbligatorio, da 1 a 9 |
| Date precise | L'utente indica solo il mese; la data di partenza la sceglie il planner (una data esatta riceve una nota che lo spiega) |
| Orari dei voli | Il primo e l'ultimo giorno hanno un'attività solo se i voli lasciano tempo (arrivo + 1,5 ore, partenza − 2,5 ore); altrimenti sono giorni di viaggio dichiarati ([ADR-0023](docs/adr/0023-giorni-di-viaggio.md)) |

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
| `services/proposal_tools.py`, `services/catalog_tools.py` | Tool delle proposte (modifiche alle varianti) e tool di sola lettura sul catalogo, in tutte le fasi |
| `llm/grounding.py` | Verifiche deterministiche sul testo dell'LLM: importi, etichette dei campi |
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
