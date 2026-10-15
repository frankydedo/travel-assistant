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
| --- | --- | --- |
| [0001](0001-controllo-ibrido-state-machine.md) | Controllo ibrido: state machine + tool calling dentro le fasi | Accettata (transizione aggiunta da 0024; tool sul catalogo da 0026) |
| [0002](0002-requisiti-strutturati-valori-flessibili.md) | Requisiti strutturati, tutti obbligatori, con valori flessibili | Accettata (estesa da 0021) |
| [0003](0003-planner-greedy-tre-varianti.md) | Planner greedy sostituibile, 3 varianti, validatore deterministico | Accettata (estesa da 0022 per «ovunque»; regola dei giorni modificata da 0023) |
| [0004](0004-rag-chroma-embedding-locali.md) | RAG con Chroma, embedding locali e filtri sui metadati | Accettata |
| [0005](0005-provider-llm-catena-fallback.md) | Adapter LLM e catena di fallback con tag del provider | Accettata (ordine sostituito da 0018, LM Studio rimosso da 0019) |
| [0006](0006-prenotazione-sicura.md) | Prenotazione sicura: conferma esplicita, transazione, idempotenza | Accettata |
| [0007](0007-guardrail-sicurezza-ai.md) | Guardrail di sicurezza specifici per l'AI | Accettata (rafforzata da 0025) |
| [0008](0008-valutazione-golden-set-judge.md) | Valutazione: golden set, metriche deterministiche, LLM-as-judge | Accettata |
| [0009](0009-storico-e-compaction.md) | Storico conversazioni e compaction automatica del contesto | Accettata |
| [0010](0010-osservabilita-langfuse-self-hosted.md) | Osservabilità con Langfuse self-hosted e pagina Tracing | Accettata (versione e API aggiornate da 0020) |
| [0011](0011-streaming-sse.md) | Streaming delle risposte via SSE | Accettata |
| [0012](0012-autenticazione-keycloak.md) | Autenticazione con Keycloak | Accettata |
| [0013](0013-dati-sintetici-deterministici.md) | Dati sintetici deterministici e fixture versionate | Accettata |
| [0014](0014-stack-e-persistenza.md) | Stack applicativo e persistenza (FastAPI, React, PostgreSQL) | Accettata |
| [0015](0015-perimetro-priorita-esclusioni.md) | Perimetro, priorità ed esclusioni consapevoli | Accettata |
| [0016](0016-guardrail-di-dominio.md) | Guardrail di dominio: rifiuto delle richieste fuori scope | Accettata (estende 0007) |
| [0017](0017-logging-strutturato.md) | Logging strutturato su stdout, separato da trace LLM e audit | Accettata |
| [0018](0018-ordine-catena-groq-prima.md) | Ordine della catena: Groq prima di Gemini | Accettata (sostituisce l'ordine di 0005) |
| [0019](0019-rimozione-lm-studio.md) | Rimozione di LM Studio dalla catena | Accettata (modifica 0005 e 0018) |
| [0020](0020-langfuse-v4-api-v2.md) | Langfuse v4 e API pubbliche v2 per la pagina Tracing | Accettata (aggiorna 0010) |
| [0021](0021-valori-qualsiasi-espliciti.md) | Valori «qualsiasi» espliciti per budget, preferenze e partenza | Accettata (estende 0002; riferimento di costo corretto da 0022) |
| [0022](0022-varianti-con-budget-illimitato-e-ovunque.md) | Varianti distinte con budget illimitato e destinazione «ovunque» | Accettata (corregge 0021, estende 0003) |
| [0023](0023-giorni-di-viaggio.md) | Giorni di viaggio: attività compatibili con gli orari dei voli | Accettata (modifica 0003) |
| [0024](0024-annullamento-riapre-la-conversazione.md) | L'annullamento di una prenotazione riapre la conversazione | Accettata (modifica 0001) |
| [0025](0025-verifiche-deterministiche-sul-testo-llm.md) | Verifiche deterministiche sul testo dell'LLM | Accettata (rafforza 0007) |
| [0026](0026-tool-di-sola-lettura-sul-catalogo.md) | Tool di sola lettura sul catalogo, in tutte le fasi | Accettata (estende 0001) |
