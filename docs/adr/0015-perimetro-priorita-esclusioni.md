# ADR-0015 — Perimetro, priorità ed esclusioni consapevoli

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges Parte D, §A12, §C3](../engineering-challenges.md#parte-d--prioritizzazione--adr-0015)

## Contesto

Il tempo a disposizione è limitato e il perimetro concordato è ampio e la traccia dice esplicitamente che una soluzione parziale, se coerente, è adeguata. Bisogna decidere in che ordine costruire e cosa escludere. Anche le esclusioni sono decisioni, e vanno motivate.

## Decisione — ordine di costruzione

**Prima una slice end-to-end funzionante con il mock, poi gli strati in ordine di valore.** Ogni fase lascia il sistema funzionante e consegnabile.

| Fase | Contenuto | Perché in questa posizione |
|---|---|---|
| 1. Slice end-to-end | Compose + Postgres, seed + indice RAG, Keycloak, state machine + slot filling (mock), planner + validatore, prenotazione, chat + card + dashboard, messaggi con tag provider | Copre tutti i requisiti obbligatori ed è dimostrabile senza chiavi |
| 2. LLM reali | Adapter, catena Gemini → Groq → LM Studio → Mock, cooldown, SSE | Il valore AI vero, con la rete di sicurezza già pronta |
| 3. Osservabilità | Langfuse self-hosted, pagina Tracing, costi stimati | Senza dati da osservare servirebbe a poco |
| 4. Qualità | Golden set, metriche, judge, CI | Misura ciò che le fasi 1-3 hanno costruito |
| 5. Memoria | Compaction, ripresa delle conversazioni | Serve solo con conversazioni lunghe |
| 6. Extra | Modifica delle prenotazioni | Utile, ma non cambia la valutazione del nucleo |

La documentazione (README, ADR, uso dell'AI) viene aggiornata durante tutte le fasi, non alla fine. Ciò che non entra entro la scadenza viene dichiarato nel README come non implementato, con il motivo.

## Decisione — esclusioni consapevoli

| Escluso | Motivazione | Quando lo riconsidererei |
|---|---|---|
| **Message broker** (Kafka / RabbitMQ) | Nessun flusso lo richiede: prenotazioni sincrone e transazionali, volumi minimi. Per il lavoro asincrono bastano le `BackgroundTasks` di FastAPI. Aggiungerlo sarebbe infrastruttura senza un bisogno. | Reindicizzazione event-driven, notifiche email, integrazione con fornitori esterni. In quel caso RabbitMQ (task queue) più di Kafka (log di eventi per volumi e replay che qui non ci sono), con outbox pattern. |
| **Upload immagini / multimodalità** | Opzionale nella traccia. Aggiunge superficie di attacco (ADR-0007) e una dipendenza da modelli vision, e non rafforza il nucleo (vincoli + conversazione). | Se le preferenze visive diventassero centrali (es. scelta dello stile degli hotel): modello vision → testo → RAG, oppure embedding CLIP. |
| **Solver ILP** | Il greedy basta su questo catalogo; l'interfaccia `Planner` rende la scelta reversibile (ADR-0003). | Catalogo grande, oppure eval che mostrano itinerari peggiori del necessario. |
| **WebSocket** | Comunicazione unidirezionale per turno: basta SSE (ADR-0011). | Funzionalità realmente bidirezionali (es. agente che interrompe l'utente, collaborazione multiutente). |
| **Agente LLM libero** | Il modello controllerebbe anche la prenotazione (ADR-0001). | Mai per le azioni con effetti collaterali; forse per l'esplorazione libera del catalogo. |
| **Langfuse Cloud / tabella `llm_calls` propria / Grafana / Langtrace** | Vedi ADR-0010. | — |
| **Login social (Google via Keycloak)** | Richiede segreti che il reviewer non ha e non rafforza il nucleo (ADR-0012). | Con utenti reali: si aggiunge in Keycloak come identity provider federato, senza toccare il backend. |
| **Pagamenti** | Fuori dallo scopo della traccia, e si portano dietro conformità e dati sensibili. | Integrazione reale, con un provider esterno (es. Stripe) e una saga. |
| **Deploy in cloud** | La consegna è una repo eseguibile in locale. | Demo pubblica. |
| **Abbonamento Claude come provider a runtime** | Non include accesso API, e i termini d'uso non consentono di usarne i token in un'app (ADR-0005). | Con una chiave API Anthropic a consumo: basterebbe un adapter in più. |

## Conseguenze

- **Positive:** in ogni momento esiste una versione consegnabile, e il reviewer vede le priorità oltre al codice.
- **Negative:** le fasi 5-6 rischiano di non entrare. È accettato e verrà dichiarato.
