# ADR-0017 — Logging strutturato su stdout, separato da trace LLM e audit

- **Stato:** Accettata
- **Riferimenti:** [ADR-0010](0010-osservabilita-langfuse-self-hosted.md) (trace LLM), [ADR-0006](0006-prenotazione-sicura.md) (prenotazioni), [ADR-0007](0007-guardrail-sicurezza-ai.md) (dati nelle trace)

## Contesto

Serve capire cosa fa il sistema e diagnosticare i problemi: richieste lente, provider in fallback, itinerari scartati dal validatore, conflitti di prenotazione. In un sistema con un LLM c'è però la tentazione di loggare tutto, prompt e messaggi compresi, mischiando diagnosi, dati personali e contenuti.

## Opzioni considerate

- **Destinazione:**
  - JSON su stdout raccolto da Docker;
  - stdout più Loki e Grafana nel compose;
  - OpenTelemetry con collector.
- **Contenuto:**
  - tutto, compresi messaggi e prompt;
  - solo eventi del sistema.

## Decisione

**Tre canali con scopi diversi.** Il logging è uno solo dei tre, e non sostituisce gli altri:

| Canale | Contiene | Dove |
|---|---|---|
| Log operativi | Cosa ha fatto il sistema: eventi, durate, esiti, errori | stdout, in JSON |
| Trace LLM | Prompt, risposte, token, costi | Langfuse (ADR-0010) |
| Audit di business | Messaggi, itinerari, prenotazioni con snapshot dei prezzi | PostgreSQL |

**Log operativi:**

- **JSON strutturato su stdout** (12-factor): Docker li raccoglie (`docker compose logs`), e qualsiasi piattaforma li può spedire altrove senza toccare il codice.
- **Libreria standard** (`logging` + `contextvars`), senza dipendenze aggiuntive.
- **Correlazione:** ogni riga porta `request_id` (generato o preso da `X-Request-ID`, e restituito nella risposta), `user_id` e `conversation_id`. Quando arriva Langfuse si aggiunge `trace_id`.
- **Eventi con nome stabile**, interrogabili come campi e non come testo libero. Per esempio:
  - `http.request`, `conversation.phase_changed`;
  - `llm.call` (provider, modello, latenza, token, tentativi) e `llm.provider_failed`;
  - `planner.completed`, `planner.infeasible`, `validator.rejected`;
  - `booking.confirmed`, `booking.conflict`, `booking.idempotent_replay`, `booking.cancelled`;
  - `guardrail.out_of_scope`, `ratelimit.exceeded`, `auth.invalid_token`.
- **Mai il contenuto:** né il testo dei messaggi, né i prompt, né i token di autenticazione. Un test lo verifica.
- **Configurazione da env:** `LOG_LEVEL`, e `LOG_FORMAT` (`json` in Docker, `console` leggibile in sviluppo).

## Motivazione

- **I log servono a diagnosticare, non a conservare contenuti.** Tenere fuori i messaggi elimina il problema dei dati personali sparsi in un canale che di solito ha retention e accessi meno controllati.
- **Gli eventi con nome stabile** rendono i log utili anche senza uno strumento dedicato (`docker compose logs backend | grep booking.conflict`) e pronti per qualunque piattaforma.
- **Loki/Grafana e OpenTelemetry sono stati scartati per questo perimetro:** container in più e sovrapposizione con Langfuse (Grafana era già tra le esclusioni di ADR-0010).

## Conseguenze

- **Positive:** zero infrastruttura aggiuntiva, correlazione da una richiesta fino alla sua trace, nessun dato personale nei log.
- **Negative:** non ci sono ricerca e dashboard sui log; per le metriche LLM c'è Langfuse.
- **Evoluzione:** il formato JSON con campi stabili si collega così com'è a Loki, ELK, Datadog o a un collector OpenTelemetry.
