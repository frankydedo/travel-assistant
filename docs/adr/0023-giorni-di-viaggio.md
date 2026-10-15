# ADR-0023 — Giorni di viaggio: attività compatibili con gli orari dei voli

- **Stato:** Accettata (modifica la regola «un'attività per ogni giorno» di [ADR-0003](0003-planner-greedy-tre-varianti.md))

## Contesto

La traccia chiede un'attività per ogni giorno. Planner e validatore la applicavano alla lettera, ignorando gli orari dei voli. In una conversazione reale l'itinerario per il Giappone metteva uno street food al mercato di Tsukiji il primo giorno con arrivo all'01:25 del giorno dopo, e nella Sicilia una serata alla Vucciria con il volo di ritorno alle 19:05. Il prezzo di quelle attività veniva pagato, ma non si potevano fare.

## Opzioni considerate

1. **Solo voli compatibili**: un'attività ogni giorno resta un vincolo rigido e i voli che non lasciano tempo vengono scartati. Rispetta la traccia alla lettera, ma con i voli notturni il Giappone diventerebbe quasi sempre infattibile.
2. **Primo e ultimo giorno sempre liberi**: semplice, ma toglie due attività anche quando i voli lo permetterebbero.
3. **Voli compatibili quando esistono, altrimenti giorno di viaggio dichiarato.**

## Decisione

Opzione 3, scelta con l'utente:

- **Finestra libera:** primo giorno da arrivo + 1,5 ore (passaporti, trasferimento) fino alle 22:00, oppure nessuna ora se si atterra dopo mezzanotte; ultimo giorno dalle 9:00 fino a 2,5 ore prima del decollo. Un'attività ci sta se la sua durata entra nella finestra.
- **Scelta dei voli:** per ogni data il planner prende il volo più economico che lascia tempo almeno per l'attività più breve disponibile; se non ce n'è nessuno prende il più economico in assoluto, e quel giorno diventa un **giorno di viaggio** senza attività.
- **Garanzie:** il validatore rifiuta un'attività del primo o dell'ultimo giorno che non entra nella finestra, e continua a pretendere un'attività in ogni giorno intermedio. Le sostituzioni via tool rispettano la stessa finestra.
- **Trasparenza:** card, risposta e dati per l'LLM indicano i giorni di viaggio con l'orario del volo.

## Motivazione

Proporre e far pagare un'attività che non si può fare è peggio che lasciare un giorno libero e dirlo. Preferire i voli compatibili mantiene la richiesta della traccia ogni volta che è realizzabile.

## Conseguenze

- **Positive:** nessuna attività impossibile; la deviazione dalla traccia è limitata ai casi in cui non esiste un volo compatibile ed è dichiarata.
- **Negative:** il volo compatibile può costare di più del più economico; il catalogo non ha l'ora di inizio delle attività, quindi si controlla solo la durata (una serata può risultare «compatibile» con un volo pomeridiano); i fusi orari sono impliciti negli orari locali del catalogo.
