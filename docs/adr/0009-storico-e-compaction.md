# ADR-0009 — Storico conversazioni e compaction automatica del contesto

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A9](../engineering-challenges.md#a9-contesto-e-memoria-conversazionale--adr-0009)

## Contesto

La history di una conversazione cresce a ogni turno. Mandarla tutta all'LLM aumenta token, costi e latenza, e prima o poi supera i limiti di contesto o di token al minuto dei free tier. D'altra parte, lo storico delle conversazioni è una funzionalità utile all'utente (opzionale nella traccia).

## Opzioni considerate

- **Gestione del contesto:** troncamento · finestra scorrevole · riassunto (compaction).
- **Momento della compaction:** a ogni turno · al superamento di una soglia.

## Decisione

**Storico conversazioni implementato:**

- tutti i messaggi sono persistiti con ruolo, testo, provider e modello (ADR-0005) e ID della trace;
- l'utente vede l'elenco delle proprie conversazioni e può riprenderle.

**Compaction automatica:**

- prima di ogni chiamata LLM si stima la dimensione del contesto. Se supera una **soglia configurabile** (default circa 8k token), i messaggi precedenti vengono **riassunti dall'LLM**;
- il **riassunto diventa il nuovo contesto di partenza**, seguito dagli ultimi scambi in forma integrale, che preservano la continuità immediata;
- il riassunto è salvato come evento della conversazione, così la compaction è ispezionabile ed è tracciata in Langfuse.

**Cosa non viene mai riassunto:**

- lo stato strutturato (`TripRequirements`, itinerari proposti, stato della fase), che è iniettato sempre per intero (ADR-0002);
- lo storico visibile all'utente: la compaction riguarda solo ciò che si manda all'LLM.

## Motivazione

- I dati che contano davvero vivono nello stato strutturato e non nel testo, quindi un riassunto imperfetto non può far perdere un requisito o un prezzo.
- La soglia, invece di una compaction a ogni turno, evita chiamate LLM inutili nelle conversazioni brevi, che sono la maggioranza.
- Il troncamento semplice perderebbe il contesto delle preferenze espresse all'inizio.

## Conseguenze

- **Positive:** contesto limitato, costi prevedibili, storico completo per l'utente.
- **Negative:** la compaction è una chiamata LLM in più e può fallire. In quel caso si ripiega sul troncamento.
- **Da verificare:** la soglia, da tarare sui limiti effettivi dei modelli free tier.
