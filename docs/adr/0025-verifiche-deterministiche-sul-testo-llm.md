# ADR-0025 — Verifiche deterministiche sul testo dell'LLM

- **Stato:** Accettata (rafforza [ADR-0007](0007-guardrail-sicurezza-ai.md))

## Contesto

Nelle conversazioni con gli LLM reali (Groq) tutti i dati calcolati dal codice erano corretti, ma il testo libero dell'LLM no:

- **Prezzo cambiato:** l'LLM aveva 1963 € nei dati e ha scritto «1 966 €».
- **Servizi inventati:** a una domanda sulle Terme Segestane ha risposto con «saune, idromassaggi, massaggi, trattamenti a pagamento», assenti dal catalogo. La ricerca semantica non aveva trovato l'attività nemmeno con il suo nome nella domanda, e il modello ha riempito il vuoto.
- **Scelta mancata:** a «prenota tu la bilanciata» ha risposto a parole senza chiamare `select_variant`, nominando un pulsante di conferma che non compariva.
- **Silenzi:** una variante mancante non veniva spiegata.

L'istruzione «usa solo i dati forniti» nel prompt non basta.

## Decisione

- **Controllo degli importi.** Ogni importo in euro scritto dall'LLM deve essere un numero presente nei dati che il codice gli ha dato, o la differenza tra due di essi. Se non lo è, la risposta viene sostituita dal testo scritto dal codice (tag `SYSTEM`) e l'evento va nei log (`llm.ungrounded_amount`) e nella trace come guardrail.
- **Ricerca ibrida per le domande sulle attività.** `search_activities` mette prima le attività il cui nome compare nella domanda e poi ordina per similarità semantica. I dettagli di una variante includono le descrizioni del catalogo, e il prompt chiede di dire «nel catalogo non è indicato» quando un dettaglio manca.
- **Scelta esplicita.** Se l'utente nomina una variante con un verbo di scelta o di prenotazione («scelgo», «prendo», «prenota…») senza chiedere modifiche, e l'LLM non chiama `select_variant`, la selezione la fa il codice. La prenotazione resta solo dal pulsante (ADR-0006).
- **Fatti al posto dei silenzi.** Il codice passa alla risposta il motivo delle varianti mancanti, i giorni di viaggio (ADR-0023) e ciò che ha già capito dei requisiti.

## Motivazione

Coerente con il principio del progetto: l'LLM spiega, ma ciò che può essere verificato in modo deterministico viene verificato dal codice. Un prezzo sbagliato in chat è un errore grave anche se le card e la prenotazione usano il prezzo giusto.

## Conseguenze

- **Positive:** nessun importo inventato arriva all'utente; le domande su un'attività nominata trovano la sua descrizione.
- **Negative:** il controllo copre gli importi, non le affermazioni qualitative (es. «più tranquilla»), che restano affidate al prompt e alle eval (ADR-0008); una risposta corretta ma con un calcolo non previsto (es. un prezzo a persona ricavato a mente) viene sostituita dal testo del codice, più povero.
