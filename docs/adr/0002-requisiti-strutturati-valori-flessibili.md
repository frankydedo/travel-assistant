# ADR-0002 — Requisiti strutturati, tutti obbligatori, con valori flessibili

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A2, §B1](../engineering-challenges.md#a2-raccolta-requisiti-slot-filling--adr-0002)

## Contesto

La traccia chiede di raccogliere budget, nazione, preferenze e mese. Per costruire un itinerario servono però anche dati che **la traccia non specifica**: durata, aeroporto di partenza, numero di viaggiatori e date precise. Il linguaggio naturale è inoltre ambiguo ("tipo 1500€", "qualcosa di caldo") e soggetto a correzioni ("anzi facciamo luglio").

## Opzioni considerate

1. **Ricavare i requisiti dalla history** a ogni turno.
2. **Oggetto strutturato persistito**, aggiornato a ogni turno.
3. Per i campi mancanti nella traccia: **default silenziosi** (1 viaggiatore, 7 notti, partenza da Roma) oppure **campi obbligatori** da chiedere all'utente.

## Decisione

Lo stato è un oggetto **`TripRequirements`** persistito per conversazione. A ogni turno l'LLM produce un **aggiornamento parziale** in output strutturato, validato da Pydantic e unito allo stato esistente.

**Tutti i campi sono obbligatori e partono a `null`.** La fase di raccolta termina solo quando sono tutti valorizzati. Alcuni accettano valori flessibili:

| Campo | Valori ammessi | Validazione |
|---|---|---|
| `budget_total` | importo in € | > 0 |
| `destination` | `{type: country, code}` · `{type: suggest}` · `{type: anywhere}` | paese presente nel catalogo |
| `preferences` | categorie + testo libero | almeno una categoria tra quelle note |
| `month` | mese | si usa la prossima occorrenza del mese coperta dal catalogo; il viaggio si svolge interamente nel mese quando possibile, altrimenti inizia nel mese e può finire nel successivo |
| `duration_days` | `{min, max}` (min = max se fisso) | 2 ≤ min ≤ max ≤ 14 |
| `departure_airport` | codice IATA | presente nel catalogo |
| `travelers` | intero | ≥ 1 |

Semantica dei valori flessibili:

- **"Consigliami tu" (`suggest`)**: il codice calcola i paesi **fattibili** (mese, budget, aeroporto di partenza). L'LLM ne sceglie uno in base alle preferenze e spiega perché. La scelta viene salvata come `country` ed è modificabile.
- **"Ovunque" (`anywhere`)**: nessun filtro sul paese. Il planner valuta tutte le destinazioni e la scelta è deterministica.
- **Date flessibili**: l'utente indica solo mese e durata. Data di partenza e durata esatta le sceglie il planner (ADR-0003).

Assunzioni sul modello di costo, da documentare nel README:

- "N giorni" = N-1 notti, con un'attività per ciascuno degli N giorni;
- voli e attività hanno prezzo a persona;
- una camera ospita 2 persone (camere = ⌈viaggiatori / 2⌉);
- il budget è totale per tutto il gruppo.

## Motivazione

- Lo stato strutturato rende le correzioni banali (si sovrascrive un campo) e mantiene piccolo il contesto mandato all'LLM (ADR-0009).
- I campi obbligatori evidenziano il gap della traccia invece di nasconderlo dietro default arbitrari che l'utente non ha scelto.
- I valori flessibili riflettono il modo in cui le persone pianificano davvero un viaggio, e affidano la scelta fine al planner, che la fa meglio.
- Limitare "consigliami tu" ai paesi fattibili impedisce all'LLM di proporre una destinazione che poi il planner non riesce a soddisfare.

## Conseguenze

- **Positive:** stato ispezionabile e testabile, estrazione misurabile campo per campo (ADR-0008).
- **Negative:** più turni di raccolta. Va mitigato chiedendo più campi mancanti nella stessa domanda.
- **Da verificare:** la qualità dell'estrazione strutturata con i modelli free tier. Il mock usa regole (regex e keyword) e funge da baseline.
