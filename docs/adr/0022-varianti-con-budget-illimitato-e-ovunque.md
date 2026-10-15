# ADR-0022 — Varianti distinte con budget illimitato e destinazione «ovunque»

- **Stato:** Accettata (corregge il costo di riferimento di [ADR-0021](0021-valori-qualsiasi-espliciti.md) ed estende [ADR-0003](0003-planner-greedy-tre-varianti.md) per «ovunque»)

## Contesto

La prima conversazione con budget illimitato, destinazione «ovunque», qualsiasi aeroporto e nessuna preferenza ha prodotto tre varianti deludenti:

- **Economica e Bilanciata quasi identiche** (645 € e 646 €, stesso hotel 2★). Il costo di riferimento scelto in ADR-0021, il doppio del viaggio più economico, era troppo basso: la penalità sul prezzo diventava così alta che la Bilanciata si comportava come l'Economica.
- **Tre volte la stessa meta.** Senza preferenze tutte le mete hanno la stessa qualità delle attività, e a parità di qualità vince il prezzo: anche la Premium finiva in Sicilia. Chi dice «ovunque» si aspetta di vedere mete diverse.
- **Nessuna spiegazione:** la risposta non diceva che il budget era illimitato né quali mete e aeroporti erano stati confrontati.

## Decisione

- **Costo di riferimento = costo della Premium.** Senza budget il planner pianifica prima la strategia che guarda solo la qualità (non dipende dai prezzi, quindi non dipende dal riferimento) e ne usa il prezzo per pesare costo e qualità nelle altre due. La Bilanciata sta così tra l'Economica e la Premium.
- **Con «ovunque», un paese diverso per variante quando possibile.** Le varianti vengono scelte in ordine (Economica, Bilanciata, Premium): ognuna prende il suo itinerario migliore in un paese non ancora usato e, se non ce n'è uno valido, accetta lo stesso paese. Con una destinazione precisa o «consigliami tu» il comportamento di ADR-0003 non cambia.
- **Le scelte fatte per conto dell'utente vengono dette.** Il codice scrive le frasi (`scelte_del_sistema`: budget illimitato, paesi e aeroporti confrontati, nessuna preferenza) e il motivo di ogni variante (`perché`); l'LLM le usa nella risposta, il mock le riporta così come sono.

## Motivazione

Le varianti servono a dare all'utente una scelta vera. Due varianti identiche, o tre proposte nello stesso posto quando l'utente ha detto «ovunque», sprecano quella scelta. Il riferimento basato sulla Premium misura il prezzo sullo stesso intervallo che l'utente vede nelle card.

## Conseguenze

- **Positive:** varianti distinte anche senza vincoli; con «ovunque» tre mete da confrontare; risposte che spiegano le decisioni.
- **Negative:** senza budget il planner esegue la strategia di qualità una volta in più (costo trascurabile rispetto alla preparazione delle combinazioni). Con «ovunque» la Premium può non essere nel paese di qualità più alta, se l'hanno già preso le varianti precedenti: è un compromesso dichiarato a favore della varietà.
