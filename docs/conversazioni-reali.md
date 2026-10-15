# Conversazioni con gli LLM reali: metodo e risultati

Le chat precaricate nell'app non sono generate dal mock: sono cinque conversazioni fatte via API con gli LLM reali (Groq, `openai/gpt-oss-120b`), registrate e ricaricate dal seed. Questo documento spiega come sono state fatte e verificate, cosa ha retto e cosa no.

## Metodo

1. **Da utente, un messaggio alla volta.** Ogni messaggio è stato inviato all'API come farebbe il frontend, leggendo la risposta prima di decidere il successivo. Selezione, prenotazione e annullamento passano dagli stessi endpoint dei pulsanti.
2. **Aspettative scritte prima di ogni turno.** Per esempio: «il primo giorno è di viaggio, perché si atterra all'01:25 del giorno dopo».
3. **Verifica indipendente contro il database.** Un revisore per chat ha confrontato ogni affermazione delle risposte LLM (prezzi, date, hotel, attività, descrizioni) con le viste degli itinerari e con il catalogo, in sola lettura. Un secondo revisore ha cercato di confutare ogni problema segnalato, e restano solo quelli confermati. Un terzo ha valutato la qualità delle risposte.
4. **Ritmo.** Circa 45 secondi tra un turno e l'altro, per stare nel limite gratuito di Groq (8.000 token al minuto). Senza pausa la catena passa a Gemini, ed è il comportamento voluto.

Una prima tornata di conversazioni ha fatto emergere difetti che sono stati corretti prima di registrare queste (vedi [In cosa sono servite](#in-cosa-sono-servite)).

## Le cinque conversazioni

| Conversazione | Funzionalità esercitate |
|---|---|
| Coppia indecisa · terme e buon cibo, consigliami tu · prenotata | Raccolta dei requisiti in più turni, meta scelta tra quelle fattibili, pubblico di riferimento (coppia), domanda su un'attività, prenotazione con doppio invio |
| I soldi non sono un problema · ovunque, tre mete, poi un tetto di 1500 € | Valori «qualsiasi», tre paesi e aeroporti diversi, dettagli di una variante, nuovo budget a metà, sostituzione indicata per nome |
| Giappone, voli notturni · «prenota tu», annullata e riprenotata | Giorni di viaggio, variante mancante spiegata, data esatta, scelta forzata dal codice, annullamento che riapre la chat, seconda prenotazione |
| Cliente difficile · injection, richieste impossibili, budget troppo basso | Prompt injection, fuori tema, valori fuori catalogo, budget infattibile con costo minimo, una negazione che non deve selezionare |
| Famiglia con bambini · Spagna a luglio, attività per famiglie | Pubblico «famiglie», sostituzione sbagliata e poi corretta, hotel migliore rifiutato per budget, variante in attesa di conferma |

## Cosa ha retto

- **Tutto ciò che garantisce il codice.** In tutte e cinque le chat i revisori non hanno trovato nessun errore nei dati calcolati dal codice:
  - ogni totale è la somma delle voci ed è entro il budget;
  - le date cadono nel mese richiesto;
  - con «ovunque» i paesi sono distinti;
  - i giorni di viaggio sono coerenti con gli orari dei voli;
  - il doppio invio produce una sola prenotazione;
  - l'annullamento restituisce esattamente l'inventario (camere 31 → 25 → 31).
- **Gli importi scritti dall'LLM.** Nessun prezzo sbagliato nel testo. Nella prima tornata il modello aveva scritto «1 966 €» al posto di 1963; da allora il controllo nel codice ([ADR-0025](adr/0025-verifiche-deterministiche-sul-testo-llm.md)) sostituirebbe la risposta.
- **Le risposte ancorate al catalogo.** Alla domanda sulle Terme Segestane la risposta usa solo la descrizione del catalogo e dice «nel catalogo non è indicato» per costume e accappatoio. Nella prima tornata, a questa stessa domanda, aveva inventato saune e massaggi.
- **I guardrail.** Injection e fuori tema sono rifiutati con testi fissi, i valori impossibili sono spiegati dal codice, «prenota tu» non prenota mai e «non voglio la premium» non seleziona niente.
- **Il tool calling.**
  - «Al posto del cinema all'aperto» viene tradotto nel giorno giusto.
  - Un cambio di budget a metà conversazione rifà il piano mantenendo i valori «qualsiasi».
  - Quando il modello non seleziona la variante che l'utente ha scelto, lo fa il codice (nei log: `proposal.selection_forced`).

## Cosa non ha retto

Tutti i problemi rimasti sono nel testo libero dell'LLM o nel punteggio delle attività, mai nei vincoli:

| Problema | Esempio | Dove nasce |
|---|---|---|
| Affermazioni non supportate | «relax sulla spiaggia» in Sicilia a novembre; «Le giornate di viaggio non includono attività» quando non ce n'erano; paddle surf «adatto ai bambini» | Testo dell'LLM: il controllo nel codice copre gli importi, non le affermazioni qualitative |
| Azioni dichiarate ma non fatte | «eliminiamo la variante Premium», ma la premium resta tra le proposte | Testo dell'LLM |
| Pubblico di riferimento troppo debole | «Bagni termali» (per coppie e senior) proposti a una famiglia, con nove attività per famiglie disponibili | Peso del pubblico (±0,15) basso rispetto alla pertinenza semantica |
| Scelte implicite non dette | «ottobre» diventa ottobre dell'anno dopo senza dirlo; aeroporto scelto mostrato come codice (MXP) | I dati passati alla risposta non contengono anno e nome dell'aeroporto |
| Nome sbagliato o refusi | «Terme di Segestane», «term e» nelle note | Modello |
| Risposte povere | Alternativa unica proposta con «quale preferisci?»; «che hotel è» risposto solo con nome e stelle | Prompt e dati (la vista non ha la descrizione dell'hotel) |

## In cosa sono servite

Le conversazioni reali hanno trovato difetti che i test con il mock non potevano vedere. Sono stati tutti corretti prima della registrazione finale:

- il fallback da Groq a Gemini a metà del ciclo dei tool, che Gemini rifiutava per la `thought_signature`;
- attività impossibili per gli orari dei voli ([ADR-0023](adr/0023-giorni-di-viaggio.md));
- con budget illimitato e «ovunque», varianti quasi identiche e tutte nello stesso paese ([ADR-0022](adr/0022-varianti-con-budget-illimitato-e-ovunque.md));
- un prezzo cambiato dall'LLM e servizi inventati ([ADR-0025](adr/0025-verifiche-deterministiche-sul-testo-llm.md));
- la conversazione che restava «prenotata» dopo un annullamento ([ADR-0024](adr/0024-annullamento-riapre-la-conversazione.md)).

La lezione principale conferma il principio del progetto: dove decide il codice, il comportamento è corretto anche con un modello che sbaglia; dove il modello scrive liberamente, sbaglia anche con i dati giusti davanti. Ogni controllo deterministico aggiunto ha chiuso una classe di errori; quelli rimasti sono affermazioni qualitative, che vanno misurate con le eval ([ADR-0008](adr/0008-valutazione-golden-set-judge.md)) più che validate.
