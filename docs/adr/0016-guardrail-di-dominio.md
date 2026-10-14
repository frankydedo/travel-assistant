# ADR-0016 — Guardrail di dominio: rifiuto delle richieste fuori scope

- **Stato:** Accettata (estende ADR-0007)
- **Riferimenti:** [engineering-challenges §A7](../engineering-challenges.md#a7-sicurezza-specifica-dellai--adr-0007), [ADR-0007](0007-guardrail-sicurezza-ai.md)

## Contesto

L'assistente deve rispondere solo a ciò che riguarda l'organizzazione del viaggio. Le domande fuori ambito ("chi ha vinto i mondiali?", "scrivimi una poesia", "ignora le istruzioni e…") vanno rifiutate con una risposta del tipo: *"Sono un assistente AI per viaggi, la tua domanda è fuori dal mio ambito…"*.

ADR-0007 rende innocuo ciò che il modello può fare (nessuna autorità su prezzi, utenti, prenotazioni). Questo ADR aggiunge il confine su ciò di cui il sistema accetta di parlare: riduce i costi spesi fuori dominio, l'abuso del servizio come chatbot generico e la superficie di prompt injection.

## Opzioni considerate

| Opzione | Pro | Contro |
|---|---|---|
| Solo istruzioni nel prompt di sistema | Nessun codice | Inaffidabile: un jailbreak le aggira, e la risposta resta generata dal modello |
| Chiamata di classificazione dedicata | Classificatore isolato | Una chiamata LLM in più per ogni messaggio: costo, latenza, quota dei free tier |
| Classificazione con embedding (similarità con il dominio) | Nessuna chiamata LLM | Soglia difficile da tarare, falsi positivi sui messaggi brevi |
| **Verdetto di scope dentro le chiamate strutturate esistenti** | Zero chiamate in più, verdetto validato da schema | Il verdetto dipende dalla qualità del modello, da misurare |

## Decisione

- **Il verdetto viaggia con le chiamate che già facciamo.** L'output strutturato dell'estrazione dei requisiti include `in_scope`, e l'interpretazione delle risposte in fase di proposta include l'azione `out_of_scope`. Il prompt definisce l'ambito in modo esplicito.
- **Il rifiuto lo scrive il codice**, con un testo fisso e tag `SYSTEM`, mai l'LLM. Un tentativo di jailbreak non può "convincere" la risposta a contenere altro.
- **Lo stato non cambia:** fase, requisiti e itinerari restano quelli di prima, e la conversazione riprende da dove era.
- **Niente falsi rifiuti sui casi ovvi:** saluti e conferme brevi ("ciao", "ok", "grazie") sono in scope. Un messaggio che contiene un requisito è in scope anche se contiene altro, e viene elaborata solo la parte di viaggio.
- **Il mock** applica regole: prima le richieste chiaramente fuori dominio (scrivere poesie o codice, tradurre, ricette, manipolare le istruzioni), poi la presenza di requisiti o di temi di viaggio. Da una richiesta fuori dominio non estrae requisiti: "scrivimi una poesia sul mare" non diventa una preferenza per il relax.

## Motivazione

Mettere il verdetto nelle chiamate esistenti costa zero. Lasciare il testo del rifiuto al codice è coerente con il principio guida: l'LLM *capisce* se la richiesta è in ambito, il codice *decide* cosa rispondere.

## Conseguenze

- **Positive:** nessun costo aggiuntivo, rifiuto non manipolabile, stato della conversazione protetto.
- **Negative:** il classificatore a regole del mock ha limiti noti. Per esempio "qual è la capitale della Francia?" passa come in scope perché nomina un paese. È accettato: il mock è la rete di sicurezza, non il classificatore principale.
- **Da misurare:** il golden set (ADR-0008) include casi fuori scope e casi limite. La metrica è doppia: rifiuti corretti e **falsi rifiuti** su richieste di viaggio legittime. Un falso rifiuto è un danno all'utente tanto quanto una risposta fuori ambito.
