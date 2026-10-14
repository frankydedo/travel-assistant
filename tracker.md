# Tracker

Stato di avanzamento del progetto, organizzato per le fasi di [ADR-0015](docs/adr/0015-perimetro-priorita-esclusioni.md). Legenda: `[x]` fatto · `[ ]` da fare · `[~]` in corso.

## Fase 0 — Analisi e design

- [x] Analisi delle sfide ingegneristiche ([engineering-challenges.md](docs/engineering-challenges.md))
- [x] Decisioni su tutte le sfide, con motivazioni ed esclusioni
- [x] ADR 0001-0015 ([docs/adr/](docs/adr/README.md))
- [x] Diagrammi del workflow di prenotazione ([workflow-prenotazione.md](docs/workflow-prenotazione.md))
- [x] Documento sull'uso dell'AI ([ai-usage.md](docs/ai-usage.md))
- [x] Contesto di progetto per l'agente ([CLAUDE.md](CLAUDE.md))

## Fase 1 — Slice end-to-end (con provider mock)

### Infrastruttura

- [x] Struttura del repo: documentazione in root, tutto ciò che si esegue in `project/` (compose, infra, `src/backend`, `src/frontend`)
- [x] docker-compose: Postgres, Keycloak, backend, frontend — verificato con `docker compose up --build`
- [x] `.env.example`
- [x] Realm Keycloak pre-importato (client frontend con PKCE obbligatorio, utenti di test, self-registration, audience `travel-api`)

### Dati

- [x] Modello dati (SQLAlchemy) + migrazione iniziale (Alembic)
- [x] Fixture: 5 paesi, 25 hotel, 80 attività con descrizioni e target
- [x] Seed deterministico: voli, disponibilità hotel e attività, casi limite (date esaurite, attività stagionali, giorni di chiusura)
- [x] Indicizzazione RAG in Chroma (embedding locali multilingue, filtro paese/mese) — verificata con query in italiano

### Dominio

- [x] `TripRequirements`: modello, merge, campi mancanti, validazione sul catalogo
- [x] State machine delle fasi
- [x] Planner greedy (interfaccia `Planner`, 3 varianti)
- [x] Validatore deterministico degli itinerari
- [x] Rilassamento dei vincoli per i casi infattibili
- [x] "Consigliami tu" (scelta solo tra i paesi fattibili) e "ovunque"

### AI

- [x] Astrazione per task `LLMProvider` + gateway (fallback, retry, cooldown), tag del provider su ogni messaggio
- [x] Provider mock deterministico (estrazione a regole + risposte a template)
- [x] Interprete: estrazione requisiti, interpretazione delle risposte in fase di proposta, scelta della meta, generazione testo

### API e prenotazione

- [x] Autenticazione JWT (JWKS Keycloak) + provisioning utenti just-in-time — verificata con login reale (Authorization Code + PKCE)
- [x] API conversazioni e messaggi
- [x] Selezione della variante → riepilogo con pulsante di conferma
- [x] Prenotazione: transazione, decremento condizionale, idempotency key, snapshot prezzi
- [x] Conflitto di disponibilità → 409 + nuova pianificazione automatica
- [x] Annullamento della prenotazione (ripristino inventario)
- [x] Rate limit per utente
- [x] Guardrail di dominio: rifiuto delle richieste fuori scope, stato invariato (ADR-0016)
- [x] Logging strutturato: JSON su stdout, eventi con nome stabile, correlazione per request/utente/conversazione, nessun contenuto (ADR-0017)
- [x] Provenienza AI esposta dall'API: `ai_generated` sui messaggi, `description_ai_generated` sulle attività

### Frontend

- [x] Landing page con «Accedi con SSO» / «Crea un account» (check-sso silenzioso con fallback)
- [x] Interruttore tema chiaro/scuro (solo due stati; al primo accesso il valore iniziale viene dal sistema), persistito, senza flash
- [~] Redesign moderno (Tailwind, icone, tema chiaro/scuro) con marcatura dei contenuti generati da AI

- [~] Login/registrazione via Keycloak — flusso OIDC verificato; interfaccia da provare nel browser
- [~] Chat con tag del provider
- [~] Pannello requisiti raccolti e fase corrente
- [~] Card degli itinerari (3 varianti) e pulsante di conferma
- [~] Dashboard prenotazioni
- [~] Storico conversazioni (elenco + ripresa)
- [x] Rinomina ed eliminazione delle conversazioni (le prenotazioni confermate restano)
- [x] Rendering Markdown sicuro delle risposte dell'assistente (anche durante lo streaming)

### Qualità

- [x] Unit test: estrazione del mock, requisiti, state machine, planner, validatore, gateway
- [x] Integration test API con provider mock (flusso completo, idempotenza, isolamento utenti, overbooking, annullamento, rate limit)
- [x] README: avvio, assunzioni, architettura

## Fase 2 — LLM reali

- [x] Provider OpenAI-compatibile: Gemini, Groq, LM Studio (httpx, classificazione degli errori, modelli configurabili) — verificato con chiavi reali
- [x] Catena di fallback con retry, backoff e cooldown (gateway generico, testato con provider finti)
- [x] Output strutturato adattivo: `json_schema` → `json_object` → solo prompt, validazione Pydantic e un retry con l'errore
- [x] Tool calling nativo nella fase di proposta: `select_variant`, `update_requirements`, `swap_activity`, `change_hotel`, `search_activities`, `get_itinerary_details`, `flag_out_of_scope`; loop limitato a 3 passi; verificato con Gemini e Groq reali
- [x] Streaming SSE lato backend (`progress`, `provider`, `token`, `reset`, `done`, `error`)
- [x] Streaming SSE lato client (`fetch` + `ReadableStream`, parser testato su chunk spezzati) — eventi verificati attraverso nginx senza buffering

## Fase 3 — Osservabilità

- [ ] Langfuse self-hosted nel compose, con chiavi pre-create
- [ ] Trace per turno e generation per chiamata LLM, versione del prompt
- [ ] Costo stimato a listino
- [ ] Pagina Tracing nella UI (metriche via backend)

## Fase 4 — Qualità del comportamento LLM

- [ ] Golden set (casi semplici, ambigui, flessibili, infattibili, prompt injection, fuori scope e falsi rifiuti)
- [ ] Metriche deterministiche per provider, mock come baseline
- [ ] LLM-as-judge per gli aspetti soggettivi
- [ ] CI su GitHub Actions (test + eval deterministici sul mock)

## Fase 5 — Memoria

- [ ] Compaction automatica a soglia
- [ ] Ripresa delle conversazioni con contesto compattato

## Fase 6 — Extra

- [ ] Modifica di una prenotazione esistente (con verifica disponibilità)

## Decisioni di implementazione e deviazioni

Le scelte prese durante l'implementazione che non meritano un ADR, ma che vanno rese visibili.

- **Prezzi interi in euro** ovunque: l'aritmetica del budget è esatta, senza arrotondamenti dei float.
- **Viaggio dentro il mese**: le prime prove mostravano che "agosto" diventava 31 agosto–6 settembre (settembre costa meno). Ora il viaggio si svolge interamente nel mese quando possibile (ADR-0002 aggiornato).
- **Un aeroporto di destinazione per paese** (Palermo, Barcellona, Atene, Tokyo Haneda, Reykjavik): semplifica il catalogo senza toccare il problema di fondo.
- **Voli**: si sceglie sempre il più economico per data; la qualità del volo (orari, scali) non è modellata.
- **Astrazione per task** invece che per prompt: ogni task porta il prompt per gli LLM reali e il contesto strutturato per il mock, così il mock è un vero anello della catena (ADR-0005).
- **Costo minimo stimato** (per "consigliami tu" e per i rilassamenti): stima greedy con attività distinte, non un lower bound esatto.
- **Transizione aggiunta** `AWAITING_CONFIRMATION → COLLECTING_REQUIREMENTS`, per quando l'utente cambia un requisito durante la conferma (diagramma aggiornato).
- **Conflitto di disponibilità al momento della prenotazione**: oltre al 409, il backend ricalcola subito le varianti e le aggiunge alla chat.
- **Test su PostgreSQL** (testcontainers + migrazioni reali + clone da database template per ogni test). Una prima versione girava su SQLite, in contrasto con ADR-0014: deviazione non concordata, corretta.
- **Snapshot della vista** dell'itinerario salvato in JSON, insieme alle righe `itinerary_items` usate da validatore e prenotazione.
- **Testi di rifiuto a rotazione**: invece di un unico testo, cinque testi fissi che ruotano per conversazione, più un invito adatto alla fase corrente. Il principio di ADR-0016 resta invariato: il rifiuto lo scrive il codice, non l'LLM.
- **Dipendenza async per l'autenticazione**: FastAPI esegue le dipendenze sincrone in thread separati con contesto copiato, quindi lo `user_id` impostato lì non arriverebbe ai log dell'endpoint. `get_current_user` è asincrona e delega al threadpool il lavoro bloccante.
- **Alembic e logger**: `fileConfig()` disattiva di default i logger esistenti (nei test spegneva i log dell'app); ora `disable_existing_loggers=False`.
- **Mock ≠ AI**: le risposte del mock sono regole deterministiche, quindi `ai_generated=false`; sono marcate come AI solo le risposte dei provider LLM e i testi del catalogo scritti con AI.
- **Tutti gli id sono UUID** (colonne `uuid` native in PostgreSQL, stringhe in Python): anche voli, hotel, attività, righe d'itinerario, chiave di idempotenza e `X-Request-ID`. Gli id del catalogo sono deterministici (uuid5 dallo slug del fixture o da volo e data), così il seed resta riproducibile; quelli creati a runtime sono casuali (uuid4). I codici ISO dei paesi e IATA degli aeroporti restano chiavi naturali. Gli id malformati vengono rifiutati con 422.
- **Migrazioni riunite**: il passaggio a UUID è stato fatto rigenerando un'unica migrazione iniziale invece di una conversione, perché il progetto non è mai stato rilasciato. Dopo il cambio serve `docker compose down -v`.
- **Posizione esplicita delle righe d'itinerario** (`itinerary_items.position`): con id casuali l'ordine non si può più ricavare dalla chiave.
- **Modelli scelti con un benchmark sul task reale** (estrazione di una richiesta complessa + messaggio fuori scope). `gemini-2.5-flash` restituiva 404 (ritirato per i nuovi utenti), `gemini-3.8-flash` era accurato ma lento e spesso in 503, `gemini-flash-latest` impiegava oltre 30 s; `qwen3.8-27b` estraeva vuoto. Default: `gemini-flash-lite-latest` e `openai/gpt-oss-120b`, entrambi configurabili da `.env`. Con gli alias `-latest` viene registrato il modello restituito dall'API.
- **`reasoning_effort=low`** sui modelli con ragionamento, per contenere la latenza; se un'API non lo accetta il provider smette di inviarlo.
- **Schema JSON inviato una sola volta**: era incluso tre volte (prompt dell'Interprete, suggerimento del provider, `response_format`), con circa 1.800 token per estrazione e quote dei free tier esaurite prima. Ora viaggia nel prompt solo quando il provider non supporta `json_schema`.
- **404 = provider non disponibile** (modello inesistente o ritirato), con cooldown, invece di un "formato non supportato".
- **Streaming e fallback**: se un provider fallisce dopo aver emesso token, il gateway emette `reset` e il client scarta il testo parziale prima che risponda il provider successivo.
- **Endpoint SSE con thread worker e sessione propria**: l'orchestratore è sincrono e la sessione della dipendenza FastAPI può chiudersi prima della fine dello stream; il contesto copiato mantiene `request_id` e `user_id` nei log.
- **Tool calling: l'LLM non vede mai un id**. Si riferisce a "variante + giorno" e il codice risolve il riferimento. Gli argomenti dei tool sono solo stringhe, interi ed enum, perché i provider supportano sottoinsiemi diversi di JSON Schema. Le modifiche creano un nuovo itinerario validato e quello vecchio viene scartato; i tool che cambiano fase sono terminali e restituiscono il controllo all'orchestratore.
- **`thought_signature` di Gemini 3**: le chiamate di tool vanno rimandate indietro con i campi specifici del provider, altrimenti Gemini risponde 400. Ogni tool call conserva quei campi, che vengono riallegati solo allo stesso provider che li ha prodotti.
- **Risposte in Markdown**: i prompt chiedono sempre Markdown, nel sottoinsieme che la UI mostra (grassetto, corsivo, elenchi, codice, citazioni). Il frontend non esegue HTML e non mostra link, immagini, titoli e tabelle, perché il testo di un LLM è non fidato e un link iniettato via prompt injection porterebbe ovunque. Anche mock e messaggi di sistema usano Markdown, così l'aspetto non dipende dal provider.
- **Eliminazione delle conversazioni**: messaggi e proposte non prenotate vengono cancellati davvero. Se ci sono prenotazioni confermate resta solo una riga di conversazione svuotata e nascosta (`deleted_at`), necessaria all'itinerario prenotato.
- **Limiti noti della UI**: su mobile Esc chiude insieme la finestra di conferma dell'eliminazione e il pannello laterale; se si elimina una conversazione mentre una risposta è ancora in streaming, a fine risposta la conversazione può ricomparire nell'elenco.
- **`swap_activity` con categoria esplicita**: chiedendo "qualcosa di culturale" con poco budget residuo, il sistema sceglieva l'attività più simile tra quelle economiche, cioè una corsa allo stadio (sport). Ora il tool riceve la categoria e, se nessuna attività di quella categoria è disponibile, risponde con il motivo preciso (già nel programma, non disponibile quel giorno, fuori budget) invece di sostituire con altro.
