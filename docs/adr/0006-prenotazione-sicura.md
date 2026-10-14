# ADR-0006 — Prenotazione sicura: conferma esplicita, transazione, idempotenza

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §A6](../engineering-challenges.md#a6-prenotazione-tramite-chat--adr-0006)

## Contesto

La prenotazione è l'unica azione con effetti collaterali reali. I rischi sono:

- prenotazioni non volute, con un modello che "interpreta" un sì;
- prezzi errati, se il prezzo arriva dal testo dell'LLM;
- doppie prenotazioni, da doppio click o retry;
- overbooking, con due utenti sull'ultima camera;
- disponibilità cambiata tra proposta e conferma.

## Opzioni considerate

- **Conferma:** interpretata dall'LLM dal testo · pulsante strutturato nella UI · entrambe.
- **Concorrenza:** lock pessimistico · decremento condizionale atomico · nessun controllo.
- **Atomicità multi-risorsa:** transazione DB unica · saga.

## Decisione

- Il planner salva gli itinerari proposti con stato `proposed` e un `itinerary_id`.
- La prenotazione si avvia **solo con un'azione esplicita** dell'utente: il pulsante "Prenota" sulla card dell'itinerario, oppure una conferma testuale che il backend trasforma nello **stesso pulsante da cliccare**. Il testo dell'LLM non avvia mai la prenotazione da solo.
- L'endpoint di prenotazione riceve **solo `itinerary_id` + idempotency key**. Lo `user_id` arriva dalla sessione (ADR-0007), e prezzi ed elementi vengono letti dal DB.
- **Una transazione** per volo + hotel + attività:
  - nuova verifica della disponibilità;
  - **decremento condizionale atomico** dell'inventario (`UPDATE … SET left = left - n WHERE … AND left >= n`; se le righe aggiornate non sono quelle attese, rollback);
  - **snapshot dei prezzi** sulla prenotazione.
- Se la disponibilità è cambiata, la prenotazione fallisce con un errore esplicito e il sistema **ricalcola** le varianti.
- Ciclo di vita: `proposed → confirmed → cancelled`. La cancellazione restituisce l'inventario.

## Motivazione

È il punto dove il principio guida va applicato nel modo più rigido. Il pulsante strutturato elimina l'ambiguità dell'interpretazione e funziona identico con qualsiasi provider, mock compreso. Il decremento condizionale è corretto sia sotto concorrenza sia in modo indipendente dal DB.

La saga è stata scartata perché serve quando le risorse stanno su sistemi diversi (fornitori esterni). Con un solo DB una transazione è più semplice e più forte. Va citata come evoluzione per un'integrazione reale.

## Conseguenze

- **Positive:** nessuna prenotazione senza consenso esplicito, nessun overbooking, retry sicuri.
- **Negative:** la conferma richiede un clic. È un attrito accettabile, e anzi è una garanzia per l'utente.
- **Fuori perimetro:** pagamenti e modifica di una prenotazione esistente (fase 6, ADR-0015).
