# ADR-0008 — Valutazione: golden set, metriche deterministiche, LLM-as-judge

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A8](../engineering-challenges.md#a8-valutazione-della-qualità--adr-0008)

## Contesto

Un sistema basato su LLM cambia comportamento quando cambiano prompt, modello o provider, e con la catena di fallback (ADR-0005) il provider può cambiare anche a runtime. Senza misure non si può dire se una modifica migliora o peggiora le cose.

## Opzioni considerate

- **Verifica manuale:** si provano alcune conversazioni a mano.
- **Golden set con metriche deterministiche.**
- **LLM-as-judge.**
- **Combinazione:** metriche deterministiche dove possibile, judge solo per il soggettivo.

## Decisione

Combinazione. Il **golden set** è un insieme versionato di conversazioni annotate (`evals/golden/*.yaml`) che copre:

- casi semplici e ambigui, correzioni, valori flessibili ("consigliami tu", "ovunque", intervalli di durata);
- casi infattibili (budget insufficiente) e tentativi di prompt injection.

**Metriche deterministiche**, calcolate dal codice:

- accuracy dell'estrazione **per campo** di `TripRequirements`;
- % di itinerari validi secondo il validatore (budget, disponibilità, ID esistenti): l'obiettivo è il 100%;
- comportamento corretto sui casi infattibili (rilassamenti proposti, nessun itinerario non valido);
- nessuna prenotazione avviata senza conferma.

**LLM-as-judge**, solo per ciò che non si misura via codice, con una rubrica esplicita e punteggi 1-5:

- pertinenza delle attività alle preferenze;
- chiarezza della spiegazione dell'itinerario;
- tono e utilità delle domande di chiarimento.

Altri punti:

- Gli eval girano **per provider**, con il **mock come baseline**: un LLM che non batte le regole sull'estrazione non giustifica il proprio costo.
- In **CI** girano gli eval deterministici sul mock. Quelli sui provider reali e il judge si lanciano a mano, perché consumano quota.
- I risultati vengono registrati anche in Langfuse (dataset + punteggi), così si confrontano le versioni dei prompt.

## Motivazione

Le parti deterministiche coprono le garanzie critiche (vincoli, sicurezza) con certezza e a costo zero. Il judge costa ed è a sua volta rumoroso, quindi resta confinato agli aspetti dove è l'unico strumento disponibile.

## Conseguenze

- **Positive:** le regressioni si vedono, i provider si confrontano, il valore dell'LLM rispetto alle regole si misura.
- **Negative:** il golden set va mantenuto. Il judge è influenzato dal modello che giudica, quindi va dichiarato quale modello è e accettato come limite.
- **Da decidere:** la dimensione del golden set compatibile con la scadenza. L'obiettivo è circa 20-30 casi.
