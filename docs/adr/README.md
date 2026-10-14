# Architecture Decision Records

Ogni decisione architetturale rilevante è registrata in un file a sé, con il formato:

- **Stato**: `Proposta`, `Accettata`, `Sostituita da ADR-XXXX` o `Deprecata`.
- **Contesto**: il problema e i vincoli.
- **Opzioni considerate**: le alternative valutate, comprese quelle scartate.
- **Decisione**: cosa si fa.
- **Motivazione**: perché questa opzione e non le altre.
- **Conseguenze**: cosa si guadagna, cosa si paga e cosa resta da verificare.

Una decisione accettata non si modifica: se cambia, si scrive un nuovo ADR che la sostituisce. La vista d'insieme delle sfide è in [`../engineering-challenges.md`](../engineering-challenges.md).

## Principio guida

> **L'LLM capisce e spiega, il codice decide e garantisce.**

Quasi tutti gli ADR applicano questo principio a un punto specifico del sistema.

## Indice

| # | Titolo | Stato |
|---|---|---|
| [0001](0001-controllo-ibrido-state-machine.md) | Controllo ibrido: state machine + tool calling dentro le fasi | Accettata |
| [0002](0002-requisiti-strutturati-valori-flessibili.md) | Requisiti strutturati, tutti obbligatori, con valori flessibili | Accettata |
| [0003](0003-planner-greedy-tre-varianti.md) | Planner greedy sostituibile, 3 varianti, validatore deterministico | Accettata |
| [0004](0004-rag-chroma-embedding-locali.md) | RAG con Chroma, embedding locali e filtri sui metadati | Accettata |
| [0005](0005-provider-llm-catena-fallback.md) | Adapter LLM e catena di fallback con tag del provider | Accettata |
| [0006](0006-prenotazione-sicura.md) | Prenotazione sicura: conferma esplicita, transazione, idempotenza | Accettata |
| [0007](0007-guardrail-sicurezza-ai.md) | Guardrail di sicurezza specifici per l'AI | Accettata |
| [0008](0008-valutazione-golden-set-judge.md) | Valutazione: golden set, metriche deterministiche, LLM-as-judge | Accettata |
| [0009](0009-storico-e-compaction.md) | Storico conversazioni e compaction automatica del contesto | Accettata |
| [0010](0010-osservabilita-langfuse-self-hosted.md) | Osservabilità con Langfuse self-hosted e pagina Tracing | Accettata |
| [0011](0011-streaming-sse.md) | Streaming delle risposte via SSE | Accettata |
| [0012](0012-autenticazione-keycloak.md) | Autenticazione con Keycloak | Accettata |
| [0013](0013-dati-sintetici-deterministici.md) | Dati sintetici deterministici e fixture versionate | Accettata |
| [0014](0014-stack-e-persistenza.md) | Stack applicativo e persistenza (FastAPI, React, PostgreSQL) | Accettata |
| [0015](0015-perimetro-priorita-esclusioni.md) | Perimetro, priorità ed esclusioni consapevoli | Accettata |
| [0016](0016-guardrail-di-dominio.md) | Guardrail di dominio: rifiuto delle richieste fuori scope | Accettata (estende 0007) |
| [0017](0017-logging-strutturato.md) | Logging strutturato su stdout, separato da trace LLM e audit | Accettata |
