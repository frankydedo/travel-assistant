# ADR-0024 — L'annullamento di una prenotazione riapre la conversazione

- **Stato:** Accettata (aggiunge una transizione alla macchina a stati di [ADR-0001](0001-controllo-ibrido-state-machine.md))

## Contesto

In ADR-0001 la fase `BOOKED` è terminale. Annullare una prenotazione dalla dashboard ripristinava l'inventario (ADR-0006) ma lasciava la conversazione in `BOOKED`: un nuovo messaggio riceveva «Questo viaggio è già prenotato», che a quel punto è falso.

## Decisione

- Nuove transizioni `BOOKED → PROPOSING` e `BOOKED → COLLECTING_REQUIREMENTS`, usate solo dall'annullamento.
- Se nella conversazione restano altre proposte attive si torna a `PROPOSING`; altrimenti a `COLLECTING_REQUIREMENTS` con i requisiti intatti, e il messaggio successivo produce un nuovo piano.
- Il codice aggiunge un messaggio fisso (`SYSTEM`) che dice cosa è successo e cosa si può fare.
- `BOOKED → AWAITING_CONFIRMATION` resta vietata: dopo un annullamento si riparte da una scelta, non da una conferma.

## Conseguenze

- **Positive:** la chat resta coerente con la dashboard; l'utente può riprenotare senza aprire una nuova conversazione.
- **Negative:** le proposte rimaste possono non essere più disponibili; la prenotazione le ricontrolla comunque nella sua transazione (ADR-0006).
