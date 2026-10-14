# ADR-0004 — RAG con Chroma, embedding locali e filtri sui metadati

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A4](../engineering-challenges.md#a4-rag-e-database-vettoriale--adr-0004)

## Contesto

La traccia richiede un database vettoriale con le descrizioni delle attività e i target ideali (famiglie, giovani, sportivi), per un approccio RAG. Le preferenze dell'utente arrivano in linguaggio libero e in italiano ("mi piace il mare ma anche un po' di vita notturna").

## Opzioni considerate

- **Vector DB:** Chroma embedded · Qdrant (servizio) · pgvector (in Postgres).
- **Embedding:** modello locale multilingue · API di embedding (Gemini e simili).
- **Retrieval:** similarità pura · similarità + filtri sui metadati · hybrid search (keyword + vettoriale).
- **Granularità:** chunking delle descrizioni · un documento per attività.

## Decisione

- **Chroma** in modalità embedded, persistente su volume Docker.
- **Un documento per attività**: descrizione + target + categoria. Niente chunking, le descrizioni sono brevi.
- **Embedding locali multilingue** (famiglia `sentence-transformers`, modello piccolo). Il modello viene scaricato durante la build dell'immagine e non al primo avvio.
- **Filtri sui metadati obbligatori** su paese e mese di disponibilità: la similarità ordina, ma non decide mai cosa è ammissibile. La disponibilità per data esatta la verifica comunque il planner sul DB relazionale.
- **Il DB relazionale è la fonte di verità.** Chroma contiene solo una proiezione con lo stesso ID dell'attività, e la reindicizzazione al seed è idempotente (upsert per ID).

## Motivazione

- Nessun servizio in più da gestire e nessuna quota sugli embedding, che sarebbe lo stesso problema di affidabilità di ADR-0005.
- Funziona offline, il che è coerente con il mock e con la demo senza chiavi.
- I filtri impediscono il caso tipico del RAG ingenuo: un'attività molto pertinente ma nel paese o nel periodo sbagliato.
- pgvector sarebbe elegante (un solo DB), ma Chroma rende esplicito il componente "vector DB" richiesto dalla traccia ed è più semplice da sostituire.

## Conseguenze

- **Positive:** retrieval deterministico a parità di dati, testabile, senza costi.
- **Negative:** l'immagine del backend è più pesante (modello di embedding + dipendenze). Accettato.
- **Da verificare:** la qualità del modello multilingue piccolo sulle query in italiano, misurata negli eval (ADR-0008).
