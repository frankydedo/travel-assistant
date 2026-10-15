# ADR-0026 — Tool di sola lettura sul catalogo, in tutte le fasi

- **Stato:** Accettata (estende [ADR-0001](0001-controllo-ibrido-state-machine.md))

## Contesto

A «mi dici quali sono le destinazioni disponibili?» l'assistente rispondeva con il rifiuto fisso del guardrail. Le cause erano due:

- nella raccolta dei requisiti l'unica chiamata LLM era l'estrazione, che ha giudicato fuori ambito una domanda senza requisiti;
- anche se l'avesse giudicata in ambito, in quella fase non c'era alcun modo di consultare il catalogo. ADR-0001 dava tool solo alla fase delle proposte, e quei tool sono legati alle varianti.

Un assistente di viaggio deve poter dire cosa offre: destinazioni, aeroporti, hotel, attività, disponibilità.

## Opzioni considerate

1. **Catalogo nel prompt:** migliaia di token a ogni turno, oltre il limite gratuito di Groq, e la disponibilità per data non ci sta comunque.
2. **Risposte scritte dal codice con regole:** rigide; le domande hanno troppe forme.
3. **Tool di sola lettura:** l'LLM capisce la domanda e chiede al codice i dati; il codice li legge dal database e l'LLM li spiega.

Per inserire l'opzione 3 nella raccolta dei requisiti:

- **3a, estrazione più domanda:** l'estrazione strutturata resta com'è e segnala se il messaggio è una domanda sul catalogo; solo in quel caso parte un breve ciclo di tool.
- **3b, tutto a tool calling:** anche lo slot filling diventa un ciclo di tool.

## Decisione

Opzione 3a, scelta con l'utente:

- **Cinque tool** in `app/services/catalog_tools.py`:
  - `list_destinations`;
  - `list_departure_airports`;
  - `get_hotels(paese, stelle minime)`, con prezzo per notte da/a;
  - `search_activities(richiesta, paese, mese)`, con ricerca per nome e semantica e il pubblico di riferimento;
  - `check_availability(paese, mese, partenza, viaggiatori)`: disponibilità reale (giorni con voli con posti, notti con camere, prezzi minimi, anno del mese richiesto).
- **Raccolta dei requisiti:** `Extraction` ha il campo `catalog_question`. Se è vero, i requisiti detti nello stesso messaggio vengono registrati come sempre, un ciclo di al massimo 3 passi usa i tool, e la risposta chiede anche al massimo tre dati mancanti. Se i requisiti diventano completi si passa alle proposte come di consueto.
- **Fase delle proposte:** gli stessi tool si aggiungono a quelli esistenti; `search_activities` resta quello centrato sulle varianti.
- **Ambito (ADR-0016):** le domande su cosa offre il catalogo sono esplicitamente in ambito.
- **Garanzie:**
  - i tool leggono soltanto, quindi non cambiano requisiti, fase o inventario;
  - gli argomenti sono validati;
  - la risposta passa dagli stessi controlli delle altre (importi verificati, etichette tolte, ADR-0025);
  - se il ciclo non produce una risposta, la sostituisce il riassunto scritto dal codice;
  - il mock emula la scelta del tool con regole.

## Motivazione

L'opzione 3a aggiunge una capacità senza toccare lo slot filling, che è la parte più solida (ADR-0002), e costa una chiamata LLM in più solo quando l'utente fa una domanda. I tool di sola lettura sono il caso più sicuro di tool calling: un errore dell'LLM nel scegliere il tool porta al massimo a una risposta poco utile.

## Conseguenze

- **Positive:** l'assistente risponde sul catalogo e sulla disponibilità reale in ogni fase; le risposte sono ancorate ai dati del database.
- **Negative:** una domanda costa fino a 3 chiamate LLM in più, e con il limite gratuito di Groq il fallback su Gemini scatta più spesso; il controllo nel codice copre gli importi, non le affermazioni qualitative della risposta.
