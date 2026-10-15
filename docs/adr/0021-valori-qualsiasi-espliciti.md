# ADR-0021 — Valori «qualsiasi» espliciti per budget, preferenze e partenza

- **Stato:** Accettata (estende [ADR-0002](0002-requisiti-strutturati-valori-flessibili.md); costo di riferimento corretto da [ADR-0022](0022-varianti-con-budget-illimitato-e-ovunque.md))

## Contesto

ADR-0002 rende ogni requisito obbligatorio, senza default silenziosi, e prevede già un valore flessibile per la destinazione («ovunque»). Nelle prove emergono utenti che non hanno un vincolo su altri campi: «i soldi non sono un problema», «parto da qualsiasi aeroporto», «non ho preferenze». Oggi l'assistente insiste a chiedere un valore che l'utente non ha, oppure l'LLM ne inventa uno.

## Opzioni considerate

- **Continuare a chiedere un valore preciso:** coerente con ADR-0002, ma frustrante quando il vincolo non esiste.
- **Default impliciti** (es. budget alto, aeroporto di Roma): veloce, ma è proprio il default silenzioso che ADR-0002 esclude.
- **Valori «qualsiasi» espliciti**, detti dall'utente e gestiti dal codice con regole dichiarate.

## Decisione

Tre nuovi valori, accettati solo se l'utente li esprime:

| Campo | Valore | Regola del planner |
|---|---|---|
| Budget | `budget_total = "unlimited"` | Nessun vincolo di spesa. Per pesare costo e qualità si usa un costo di riferimento, il doppio del viaggio più economico possibile, così le tre varianti restano distinte: l'economica minimizza il prezzo, la premium massimizza la qualità. |
| Preferenze | `categories = []` | Tutte le attività hanno lo stesso punteggio: decidono costo e variante. |
| Partenza | `departure_airport = "ANY"` | Il planner confronta i tre aeroporti e ogni variante parte da quello più adatto; il ritorno è sullo stesso aeroporto. |

- **Mese e durata restano come sono:** solo il mese e un intervallo di giorni. Un «qualsiasi» qui moltiplicherebbe lo spazio di ricerca (12 mesi, 13 durate) e, con budget illimitato, non avrebbe un obiettivo naturale.
- **«Non detto» e «qualsiasi» restano distinti:** un campo di cui l'utente non ha parlato resta `null` e l'assistente lo chiede.
- **Il codice verifica che il valore sia stato detto:** `keep_explicit_any` scarta un «qualsiasi» se nel messaggio dell'utente, non nella parafrasi dell'LLM, non c'è un'espressione esplicita («illimitato», «qualsiasi aeroporto», «nessuna preferenza»…). Una risposta generica come «indifferente» vale solo quando manca un solo campo, cioè quello appena chiesto.

## Motivazione

Il principio di ADR-0002 è che ogni valore usato dal planner sia una scelta dell'utente. «Qualsiasi» lo è, se l'utente lo dice. Il rischio specifico dell'AI è che l'LLM usi «qualsiasi» per riempire un buco: per questo la verifica è nel codice e non nel prompt.

## Conseguenze

- **Positive:** meno domande inutili, nessun default nascosto, regole di scelta spiegabili in risposta.
- **Negative:** con partenza «qualsiasi» lo spazio di ricerca triplica; il costo per raggiungere l'aeroporto non è modellato (assunzione dichiarata nel README); l'elenco delle espressioni riconosciute è finito e va esteso con i casi del golden set (ADR-0008).
- **Dati:** `itineraries.budget_total` diventa nullable (NULL = budget illimitato), con una migrazione dedicata.
