# ADR-0013 — Dati sintetici deterministici e fixture versionate

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §B2](../engineering-challenges.md#b2-dati-sintetici--adr-0013)

## Contesto

Servono voli, hotel, attività e disponibilità credibili per esercitare il planner e i vincoli. Il reviewer deve ottenere esattamente gli stessi dati, e il setup non deve dipendere da un LLM, che potrebbe essere in quota o assente.

## Opzioni considerate

- **Dati generati dall'LLM a ogni avvio:** non riproducibili e dipendenti dalla quota.
- **Script casuale senza seed:** non riproducibile.
- **Script deterministico + fixture testuali versionate.**

## Decisione

**Catalogo:**

- 5 paesi con stagionalità e fasce di prezzo diverse: **Italia, Spagna, Grecia, Giappone, Islanda**;
- 3 aeroporti di partenza: **FCO, MXP, NAP**;
- per paese: 1-2 aeroporti di arrivo, alcuni hotel su più fasce di prezzo, circa 12-15 attività su più categorie e target.

**Generazione:**

- **script deterministico** con seed fisso, che produce disponibilità e prezzi per data;
- il **calendario è relativo al mese di esecuzione del seed** (12 mesi in avanti), così i dati non scadono se il progetto viene valutato più tardi. A parità di mese di esecuzione, i dati sono identici;
- **stagionalità** con prezzi per alta e bassa stagione per paese (es. Islanda in estate, Giappone in primavera);
- **casi limite voluti**: date esaurite, attività stagionali, combinazioni fuori budget, per esercitare validatore e rilassamenti.

**Fixture testuali:**

- le **descrizioni e i target delle attività sono stati scritti con l'AI una sola volta**, rivisti e versionati come fixture JSON;
- il seed le carica nel DB relazionale e le indicizza in Chroma (ADR-0004).

## Motivazione

- Riproducibilità: un bug o un eval si riproducono con gli stessi dati.
- Il setup non dipende da servizi esterni.
- L'AI viene usata dove è forte e dove l'output si può rivedere una volta per tutte (testi descrittivi), non dove servirebbe determinismo (prezzi, disponibilità).

## Conseguenze

- **Positive:** dati stabili per test ed eval, avvio offline.
- **Negative:** il catalogo è piccolo e non realistico nelle dimensioni. È accettabile e dichiarato.
