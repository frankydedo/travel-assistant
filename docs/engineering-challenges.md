# Sfide ingegneristiche del progetto

> Per ogni sfida il documento riporta il problema, le opzioni valutate e la **decisione presa con la sua motivazione**. Le decisioni sono formalizzate negli ADR in [`docs/adr/`](adr/README.md), che restano il riferimento: questo documento è la vista d'insieme, gli ADR contengono il dettaglio e le conseguenze.
>
> Stato: tutte le decisioni sono prese.

## 0. Principio guida

La tensione centrale del progetto è questa: **un LLM è ottimo con il linguaggio e pessimo con i vincoli rigidi** (aritmetica del budget, disponibilità per data, integrità delle prenotazioni). Quasi ogni decisione sotto discende da una domanda: *questa responsabilità va all'LLM o al codice deterministico?*

Principio adottato: **l'LLM capisce e spiega, il codice decide e garantisce.**

---

## Parte A — Sfide di integrazione AI

### A1. Ruolo dell'LLM nell'architettura → [ADR-0001](adr/0001-controllo-ibrido-state-machine.md)

**Problema.** Quanto controllo dare al modello sul flusso della conversazione e sulla costruzione dell'itinerario.

| Approccio | Come funziona | Pro | Contro |
|---|---|---|---|
| End-to-end | L'LLM riceve catalogo/contesto e scrive l'itinerario | Semplice, "magico" | Allucinazioni (hotel inesistenti, prezzi inventati), budget sforato, non testabile |
| Agente con tool calling | L'LLM decide quali tool chiamare (`search_flights`, `book`...) | Flessibile, conversazione naturale | Non deterministico, loop imprevedibili, più token, difficile da valutare |
| Workflow / state machine + LLM | Il backend guida le fasi; l'LLM fa estrazione e generazione del testo | Prevedibile, testabile, economico | Meno flessibile su richieste fuori percorso |

**Decisione.** Ibrido: una **state machine esplicita** guida le fasi (raccolta requisiti → proposta → conferma → prenotazione) e il tool calling dell'LLM avviene solo *dentro* una fase. L'itinerario lo costruisce un **planner deterministico**, e l'LLM lo presenta e lo argomenta. In tutte le fasi l'LLM ha anche tool di **sola lettura** sul catalogo (destinazioni, aeroporti, hotel, attività, disponibilità reale), per rispondere alle domande dell'utente con i dati del database ([ADR-0026](adr/0026-tool-di-sola-lettura-sul-catalogo.md)).

**Motivazione.** Prende la prevedibilità del workflow (le transizioni critiche, come la prenotazione, non dipendono mai dal modello) senza rinunciare alla naturalezza della conversazione dentro ogni fase. Ogni fase si può testare e valutare separatamente.

**Scartati.** *End-to-end*: viola il principio guida, perché budget e disponibilità non sono garantiti. *Agente libero*: il modello controllerebbe anche la prenotazione, che è l'azione più rischiosa, ed è difficile da valutare con i modelli piccoli dei free tier.

### A2. Raccolta requisiti (slot filling) → [ADR-0002](adr/0002-requisiti-strutturati-valori-flessibili.md)

**Problema.** Estrarre i requisiti da frasi come *"ho tipo 1500€, vorrei qualcosa di caldo ad agosto, mi piace il mare ma anche un po' di vita notturna"*, gestendo ambiguità, correzioni ("anzi facciamo luglio") e validazione. La traccia, inoltre, **non specifica** durata, aeroporto di partenza, numero di viaggiatori e date precise.

**Decisione.**

- Lo stato è un oggetto strutturato `TripRequirements`, persistito e aggiornato a ogni turno con output strutturato validato da **Pydantic**.
- **Tutti i campi sono obbligatori e partono a `null`**: l'assistente continua a chiedere finché non sono tutti valorizzati. Niente default silenziosi.
- Alcuni campi accettano **valori flessibili**:

| Campo | Valori ammessi |
|---|---|
| Budget totale | importo in € (> 0) · **"illimitato"** ([ADR-0021](adr/0021-valori-qualsiasi-espliciti.md)) |
| Destinazione | un paese del catalogo · **"consigliami tu"** · **"ovunque"** |
| Preferenze attività | una o più categorie (cultura, sport, relax, nightlife, natura, gastronomia) + testo libero per il RAG · **"nessuna preferenza"** (ADR-0021) |
| Mese | un mese; la data di partenza esatta la sceglie il planner (es. "5 giorni a dicembre") |
| Durata | un valore fisso o un **intervallo** (es. 5-7 giorni) |
| Aeroporto di partenza | uno degli aeroporti del catalogo · **"qualsiasi aeroporto"** (ADR-0021) |
| Numero di viaggiatori | intero da 1 a 9 |

- **"Consigliami tu"**: l'LLM sceglie la destinazione, ma **solo tra i paesi che il codice ha già verificato come fattibili** (mese, budget, aeroporto). Spiega la scelta, che resta modificabile.
- **"Ovunque"**: nessun filtro sul paese, e il planner valuta tutte le destinazioni in modo deterministico.
- **Valori «qualsiasi»** per budget, preferenze e partenza ([ADR-0021](adr/0021-valori-qualsiasi-espliciti.md)): sono accettati solo se l'utente li dice, e il codice lo verifica sul suo messaggio. Mese e durata non hanno un «qualsiasi».

**Motivazione.** I campi obbligatori rendono esplicito il gap della traccia invece di nasconderlo dietro default arbitrari. I valori flessibili riflettono come le persone pianificano davvero un viaggio ("5-7 giorni", "consigliami tu") e spostano la scelta fine sul planner, che la fa meglio. Limitare "consigliami tu" ai paesi fattibili evita che l'LLM proponga una destinazione che poi non entra nel budget.

### A3. Generazione dell'itinerario → [ADR-0003](adr/0003-planner-greedy-tre-varianti.md)

**Problema.** Scegliere volo A/R + hotel per N notti + un'attività al giorno con `costo_volo + Σ costo_hotel + Σ costo_attività ≤ budget`, rispettando le disponibilità per data e massimizzando l'aderenza alle preferenze. È una variante di un **knapsack multi-vincolo**, resa più ampia dalla flessibilità di date e durata (A2, B1).

**Decisione.**

- **Planner greedy** dietro un'interfaccia `Planner`, sostituibile senza toccare il resto (es. con un solver ILP).
- **3 varianti** dallo stesso greedy con strategie diverse: *economica*, *bilanciata*, *premium*.
- Lo spazio di ricerca (date di partenza nel mese × durate nell'intervallo) viene esplorato in modo esaustivo, perché è piccolo; la selezione degli elementi dentro ogni combinazione è greedy.
- Ogni itinerario passa da un **validatore deterministico** (budget, disponibilità, ID esistenti) prima di arrivare all'utente.
- Se nessuna combinazione è fattibile, il sistema **rilassa i vincoli in modo guidato** ("con 1500€ in Giappone non ci stai: 4 notti invece di 6, oppure Grecia").

**Motivazione.** Il greedy è spiegabile, veloce e sufficiente su un catalogo piccolo. L'interfaccia rende la scelta reversibile. Le 3 varianti costano poco codice in più e trasformano la proposta in una scelta naturale in chat.

**Scartato (per ora).** *Solver ILP (OR-Tools / PuLP)*: l'ottimo matematico non vale la complessità con questo catalogo e questa scadenza. È il primo candidato di evoluzione.

### A4. RAG e database vettoriale → [ADR-0004](adr/0004-rag-chroma-embedding-locali.md)

**Decisione.**

- **Chroma** in modalità embedded (persistente su volume) e **un documento per attività** (descrizione + target + categoria), senza chunking.
- **Embedding locali multilingue** (famiglia `sentence-transformers`), perché le query sono in italiano.
- **Metadata filtering obbligatorio** su paese e mese: la similarità ordina, ma non decide mai cosa è ammissibile.
- Il **DB relazionale è la fonte di verità**: ID condivisi e reindicizzazione idempotente al seed.

**Motivazione.** Zero infrastruttura in più, nessuna quota sugli embedding, funziona offline. Il filtro sui metadati evita che la ricerca semantica pura proponga attività di un altro paese o di un altro periodo.

**Scartati.** *Embedding via API*: un'altra dipendenza fragile con quote, proprio il problema di A5. *Qdrant/pgvector*: validi, ma qui un servizio in più non porta vantaggi. *Hybrid search*: le descrizioni sono brevi e i filtri strutturati coprono già il caso.

### A5. Affidabilità e indipendenza dal provider → [ADR-0005](adr/0005-provider-llm-catena-fallback.md)

**Decisione.**

- **Adapter proprio** sopra l'API OpenAI-compatibile, esposta da tutti i provider scelti.
- **Catena di fallback: Gemini (Google AI Studio) → Groq → LM Studio (locale) → Mock.** L'ordine è stato poi invertito in Groq → Gemini sulla base delle latenze misurate ([ADR-0018](adr/0018-ordine-catena-groq-prima.md)), e LM Studio è stato rimosso perché nessuno lo avrebbe usato ([ADR-0019](adr/0019-rimozione-lm-studio.md)): la catena attuale è **Groq → Gemini → Mock**.
- Retry con backoff sugli errori transitori. Su `429`/quota esaurita il provider viene messo in **cooldown** (circuit breaker), così le richieste successive non perdono tempo.
- **Il mock è l'ultimo anello** ed è deterministico, basato su regole: il sistema risponde sempre, anche senza chiavi, ed è lo stesso mock usato da test e CI.
- **Trasparenza: ogni messaggio dell'assistente è salvato con il provider (e il modello) che l'ha generato, e la chat mostra un tag** `GROQ` / `GEMINI` / `MOCK` (e `SYSTEM` per i messaggi scritti dal codice).

**Motivazione.** I free tier sono inaffidabili per natura, quindi il fallback è un requisito e non un extra. Il tag rende visibile ogni degradazione invece di nasconderla: se l'utente vede `MOCK`, sa che sta parlando con il sistema di riserva. L'ordine mette per primo il provider più veloce nelle misure (Groq, ADR-0018) e in fondo l'opzione che non dipende da quote esterne.

**Nota.** L'abbonamento Claude non dà accesso API e i suoi token non si possono usare in un'app propria: è stato usato solo per lo sviluppo (vedi [`ai-usage.md`](ai-usage.md)).

**Scartato.** *LiteLLM*: ottimo, ma qui serve controllo fine su fallback, cooldown e tag del provider, e l'adapter sopra un'API comune è poco codice.

### A6. Prenotazione tramite chat → [ADR-0006](adr/0006-prenotazione-sicura.md)

**Decisione.**

- **Conferma esplicita** tramite pulsante strutturato nella UI: il testo dell'LLM da solo non avvia mai una prenotazione.
- Si prenota un `itinerary_id` **già validato dal server**: prezzi e disponibilità li decide il server.
- **Transazione unica** su volo + hotel + attività, decremento atomico dell'inventario, **idempotency key**, nuova verifica della disponibilità al momento della conferma e **snapshot del prezzo** nella prenotazione.
- Ciclo di vita: `proposed → confirmed → cancelled`.

**Motivazione.** La prenotazione è l'unica azione con effetti collaterali reali, quindi è il punto dove il principio guida va applicato in modo più rigido.

**Diagrammi.** Il flusso completo, con tutti gli attori (Interprete LLM, orchestratore, tool, validatore, conferma umana), è in [`workflow-prenotazione.md`](workflow-prenotazione.md).

**Scartato.** *Saga distribuita*: serve con servizi separati (compagnie aeree, hotel). Con un solo DB è sufficiente una transazione. Va citata come evoluzione.

### A7. Sicurezza specifica dell'AI → [ADR-0007](adr/0007-guardrail-sicurezza-ai.md)

**Decisione.**

- L'LLM **non ha autorità** su prezzi, utenti o autorizzazioni, e questa è la difesa strutturale contro la prompt injection.
- Lo `user_id` arriva sempre dalla sessione autenticata, mai da argomenti generati dal modello.
- Tool call validate contro uno schema, con verifica che gli ID esistano nel DB.
- **Rate limit per utente** e limite di lunghezza dei messaggi, per contenere l'abuso dei costi.
- Le trace contengono i messaggi utente, ma restano nel Langfuse self-hosted e non escono dall'ambiente.

**Esclusione.** *Upload di immagini* (vedi A12): eliminarlo toglie anche l'intera superficie di attacco legata ai file.

**Guardrail di dominio** → [ADR-0016](adr/0016-guardrail-di-dominio.md). L'assistente risponde solo su ciò che riguarda il viaggio, e le richieste fuori scope vengono rifiutate.

- Il verdetto di scope viaggia dentro le chiamate strutturate che già facciamo, quindi senza chiamate in più.
- Il testo del rifiuto è fisso e scritto dal codice.
- Fase e requisiti restano invariati.

### A8. Valutazione della qualità → [ADR-0008](adr/0008-valutazione-golden-set-judge.md)

**Decisione.**

- **Golden set** di conversazioni annotate con l'output atteso.
- **Metriche deterministiche**: accuracy dell'estrazione per campo, % di itinerari validi (verificabile al 100% via codice), corretta gestione dei valori flessibili e dei casi infattibili.
- **LLM-as-judge** solo per gli aspetti soggettivi: pertinenza alle preferenze, qualità della spiegazione, tono.
- Gli eval girano su ogni provider della catena. **Il mock fa da baseline**: un LLM che non batte le regole non giustifica il suo costo.

**Motivazione.** Senza misure non si può dire che una modifica al prompt o al modello migliori le cose. Separare il deterministico dal soggettivo tiene il judge dove serve davvero, perché è costoso e a sua volta rumoroso.

### A9. Contesto e memoria conversazionale → [ADR-0009](adr/0009-storico-e-compaction.md)

**Decisione.**

- **Storico conversazioni implementato**: tutti i messaggi sono persistiti, con il tag del provider, e si può riprendere una conversazione.
- **Compaction automatica**: quando il contesto stimato supera una soglia configurabile (default ~8k token), i messaggi precedenti vengono riassunti dall'LLM e **il riassunto diventa il nuovo contesto di partenza**, insieme agli ultimi scambi in forma integrale.
- Lo **stato strutturato** (requisiti, itinerari) non viene mai riassunto: è iniettato sempre per intero.
- La compaction riguarda solo ciò che si manda all'LLM. **Lo storico visibile all'utente resta completo.**

**Motivazione.** Contiene token e costi, rispetta i limiti di contesto e di token al minuto dei free tier, e non perde i dati che contano, perché quelli vivono nello stato strutturato e non nel testo.

### A10. Osservabilità e costi → [ADR-0010](adr/0010-osservabilita-langfuse-self-hosted.md)

**Decisione.**

- **Langfuse self-hosted** in docker-compose, con organizzazione, progetto e chiavi **pre-create all'avvio**: il tracing funziona con `docker compose up`, senza account.
- Ogni turno di chat è una trace, e ogni chiamata LLM (estrazione, risposta, judge, compaction) è una generation con provider, modello, token, latenza, esito e fallback.
- **Pagina "Tracing" nella UI** con le metriche lette dall'API di Langfuse tramite il backend (le chiavi non arrivano al frontend): chiamate e token per provider, latenza, tasso di fallback ed errori, costo stimato.
- **Costo stimato a listino**: i free tier costano 0€, quindi il costo viene calcolato da una tabella prezzi di riferimento e inviato a Langfuse. Mostra quanto costerebbe il sistema in produzione.
- Versione del prompt registrata in ogni trace.

**Motivazione.** Langfuse è lo standard open source per il tracing LLM. Il self-hosting toglie la dipendenza dalle chiavi del reviewer, e la pagina in UI rende l'analisi dei costi parte del prodotto.

**Scartati.** *Langfuse Cloud*: il reviewer dovrebbe avere un account. *Tabella `llm_calls` propria*: duplicherebbe Langfuse. *Langtrace*: meno diffuso, nessun vantaggio qui. *Grafana*: metriche di sistema, non specifiche per LLM.

**Costo accettato.** 5 container in più (ClickHouse, Redis, MinIO, web, worker; il database di Langfuse sta nella stessa istanza PostgreSQL) e più RAM, documentata nel README.

**Logging** → [ADR-0017](adr/0017-logging-strutturato.md). Tre canali con scopi diversi:

- log operativi in JSON su stdout, con eventi dal nome stabile, correlati per `request_id`, utente e conversazione, e senza mai il contenuto dei messaggi;
- trace LLM in Langfuse;
- audit di business nel database.

### A11. Latenza e UX → [ADR-0011](adr/0011-streaming-sse.md)

**Decisione.**

- **Streaming via SSE**, con eventi di avanzamento ("cerco voli… cerco hotel…").
- Itinerari renderizzati come **card dal JSON strutturato**, non dal testo dell'LLM.
- Lato client lo stream si legge con `fetch` + `ReadableStream`, perché l'`EventSource` nativo non permette di inviare l'header `Authorization` con il token.

**Scartato.** *WebSocket*: la comunicazione è unidirezionale (server → client) per turno, quindi la bidirezionalità non serve e aggiunge complessità.

### A12. Multimodalità — esclusa

**Decisione.** Nessun upload di immagini e nessuna analisi multimodale.

**Motivazione.** È opzionale nella traccia, aggiunge superficie di attacco (A7) e una dipendenza da modelli vision, e non rafforza il nucleo del problema (vincoli + conversazione). Il tempo va sulle parti obbligatorie e sugli eval. Vedi [ADR-0015](adr/0015-perimetro-priorita-esclusioni.md).

---

## Parte B — Sfide di sistema

### B1. Modello dati e date flessibili → [ADR-0002](adr/0002-requisiti-strutturati-valori-flessibili.md), [ADR-0003](adr/0003-planner-greedy-tre-varianti.md)

**Decisione.**

- **Inventario per data**: `hotel_availability(hotel_id, date, rooms_left, price)` e analoghe per voli e attività. Semplifica i controlli e il decremento atomico.
- **Date flessibili**: l'utente indica mese e durata ("5 giorni a dicembre"). Il viaggio si svolge **interamente nel mese indicato** quando possibile; altrimenti inizia nel mese e può finire nel successivo.
- Itinerario come entità con elementi polimorfici (`ItineraryItem`: volo, hotel, attività).
- **Assunzioni da documentare nel README**:
  - "N giorni" = N-1 notti, con un'attività per ciascuno degli N giorni;
  - voli e attività hanno prezzo a persona;
  - una camera d'hotel ospita 2 persone (camere = ⌈viaggiatori / 2⌉).

### B2. Dati sintetici → [ADR-0013](adr/0013-dati-sintetici-deterministici.md)

**Decisione.**

- **5 paesi** con stagionalità e fasce di prezzo diverse: Italia, Spagna, Grecia, Giappone, Islanda.
- Partenza da 3 aeroporti italiani (FCO, MXP, NAP).
- Prezzi per mese (alta e bassa stagione) e **date volutamente esaurite** per esercitare i vincoli.
- **Script deterministico** (seed fisso). Il calendario è relativo al mese di esecuzione del seed, così i dati non "scadono".
- **Descrizioni delle attività scritte con l'AI una sola volta** e versionate come fixture JSON: il setup non dipende da un LLM.

### B3. Esperienza del reviewer

**Decisione.** `docker compose up` deve funzionare subito: seed automatico, `.env.example`, Keycloak con realm pre-importato, Langfuse con chiavi pre-create, mock come rete di sicurezza. Con il compose completo serve più RAM, e va dichiarato nel README.

### B4. Testing

**Decisione.**

- Unit test su planner, validatore e state machine.
- Integration test sulle API con il provider mock.
- Eval separati (A8) per il comportamento dell'LLM.
- CI su GitHub Actions per test ed eval sul mock.

### B5. Stack e persistenza → [ADR-0014](adr/0014-stack-e-persistenza.md)

**Stack.** FastAPI + React.

**Persistenza.** **PostgreSQL** invece di SQLite. Langfuse self-hosted richiede comunque Postgres, quindi non aggiunge infrastruttura. Offre lock di riga per la concorrenza delle prenotazioni ed è più realistico. Una sola istanza Postgres, con database separati per app, Keycloak e Langfuse.

---

## Parte C — Proposte aggiuntive

### C1. Autenticazione → [ADR-0012](adr/0012-autenticazione-keycloak.md)

**Decisione.**

- **Keycloak** in docker-compose con realm pre-importato (utenti di test, self-registration attiva).
- Il frontend usa OIDC Authorization Code + PKCE. Il backend valida solo i JWT e registra l'utente nel proprio DB al primo accesso (dal claim `sub`).

**Motivazione.** Standard OIDC, registrazione e login già pronti (requisito della traccia), backend indipendente dall'identity provider.

**Scartati.** *JWT fatto in casa*: reinventa la sicurezza. *Google SSO*, diretto o federato in Keycloak: richiede segreti che il reviewer non ha e non aggiunge valore al nucleo. Se servisse, si aggiungerebbe in Keycloak senza toccare il backend.

### C2. Osservabilità LLM

Decisa in A10: Langfuse self-hosted + pagina di tracing nella UI.

### C3. Message broker (Kafka / RabbitMQ) — escluso → [ADR-0015](adr/0015-perimetro-priorita-esclusioni.md)

**Decisione.** Nessun broker.

**Motivazione.** In questo perimetro non c'è un flusso che lo richieda: le prenotazioni sono sincrone e transazionali, e i volumi sono minimi. Aggiungerlo sarebbe infrastruttura senza un bisogno reale. Per il lavoro asincrono bastano le `BackgroundTasks` di FastAPI.

**Quando servirebbe.** Reindicizzazione event-driven del vector DB, notifiche di conferma via email, eventi di utilizzo verso un sistema di analytics, integrazione con fornitori esterni. In quel caso sceglierei RabbitMQ (semantica task queue) rispetto a Kafka (log di eventi, pensato per volumi e replay che qui non ci sono), con un *outbox pattern* per non perdere eventi.

### C4. Aggiunte che mostrano il ragionamento ingegneristico

Tutte approvate:

1. **ADR** per ogni decisione, in [`docs/adr/`](adr/README.md).
2. **Eval eseguibili** + CI (A8).
3. **Validatore deterministico** degli itinerari (A3).
4. **Documento sull'uso dell'AI**: [`docs/ai-usage.md`](ai-usage.md).
5. **Assunzioni esplicite** sui requisiti (A2, B1).
6. **Rate limit per utente** (A7).
7. **Mock + demo offline** (A5).

---

## Parte D — Prioritizzazione → [ADR-0015](adr/0015-perimetro-priorita-esclusioni.md)

**Strategia.** Con un tempo a disposizione limitato, l'ordine è: **prima una slice end-to-end funzionante con il mock, poi gli strati in ordine di valore.** Quello che non entra viene documentato come non fatto, con il motivo.

| Fase | Contenuto |
|---|---|
| **1. Slice end-to-end** | Compose + Postgres, seed + indice RAG, Keycloak, state machine + slot filling (mock), planner greedy + validatore, prenotazione, chat + card itinerario + dashboard prenotazioni, persistenza messaggi con tag provider |
| **2. LLM reali** | Adapter + catena Groq → Gemini → Mock, cooldown, streaming SSE |
| **3. Osservabilità** | Langfuse self-hosted, pagina Tracing nella UI, costi stimati |
| **4. Qualità** | Golden set, metriche deterministiche, LLM-as-judge, CI |
| **5. Memoria** | Compaction automatica, ripresa delle conversazioni |
| **6. Extra** | Modifica delle prenotazioni |

**Esclusioni consapevoli** (dettaglio in ADR-0015): message broker, upload immagini / multimodalità, solver ILP, WebSocket, agente LLM libero, login social, pagamenti, deploy cloud, abbonamento Claude come provider a runtime.
