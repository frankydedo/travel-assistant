# Come ho usato l'AI generativa

> Documento vivo, aggiornato durante lo sviluppo e non ricostruito alla fine. La traccia indica che il **modo** di usare l'AI è parte della valutazione, quindi qui documento cosa ho delegato, cosa ho deciso io, dove ho corretto il modello e come ho verificato i risultati.

## In sintesi

- **L'AI ha accelerato tutto ciò che è esplorazione, stesura e implementazione**: analisi del problema, alternative, bozze di documenti, codice, dati sintetici.
- **Le decisioni sono mie.** L'AI propone opzioni con pro e contro; io scelgo, modifico o scarto, e ogni decisione è registrata in un ADR con la sua motivazione.
- **Nessun output dell'AI viene accettato senza verifica**: rileggo i diff, eseguo test ed eval, e controllo sulle fonti le affermazioni fattuali (limiti dei provider, API).
- **Il contesto per l'AI è un artefatto versionato** (`CLAUDE.md`, ADR, documento delle sfide), così il comportamento dell'agente resta coerente e riproducibile tra una sessione e l'altra.

## Due livelli: l'AI nello sviluppo e l'AI nel prodotto

| | AI nello sviluppo | AI nel prodotto |
|---|---|---|
| **Cosa** | Assistente di ingegneria: analisi, documenti, codice | Componente del sistema: comprensione della chat e spiegazione degli itinerari |
| **Strumento** | Claude Code (in VS Code) con l'abbonamento Claude | Gemini → Groq → LM Studio → Mock (ADR-0005) |
| **Principio** | L'AI propone, io decido e verifico | L'LLM capisce e spiega, il codice decide e garantisce |

Il parallelo è voluto: **in entrambi i livelli l'AI non ha l'ultima parola sulle cose che devono essere corrette.** Nello sviluppo l'ultima parola spetta a me e ai test, nel prodotto al codice deterministico.

## Strumenti e perché

- **Claude Code** (agente in VS Code): lavora direttamente sul repository, legge e scrive i file, esegue i comandi. L'ho usato con modelli diversi in base al compito, cambiando modello durante la sessione.
- **Abbonamento Claude solo per lo sviluppo.** Ho valutato di usarlo anche come LLM dell'applicazione. Ho verificato però che l'abbonamento non include accesso API e che i termini d'uso non consentono di usarne i token dentro un'app, quindi a runtime uso i free tier (ADR-0005).
- **Free tier a runtime** (Google AI Studio, Groq) + **LM Studio** in locale + **mock**: nessun costo, come richiesto dalla traccia.

## Divisione dei ruoli

| Attività | Cosa ha fatto l'AI | Cosa ho fatto io |
|---|---|---|
| Formalizzazione della traccia | Conversione in Markdown strutturato | Scelta di tenerla fuori dalla repo consegnata |
| Analisi del problema | Elenco delle sfide ingegneristiche con opzioni e trade-off | Indicazione del focus (ragionamento da AI Engineer, non bravura nel codice); proposte aggiuntive (Keycloak, Langfuse, broker) |
| Decisioni architetturali | Opzioni, rischi, domande sui punti ambigui | **Tutte le scelte**, con modifiche rispetto alle proposte (vedi registro sotto) |
| Documentazione (ADR, questo file) | Stesura a partire dalle decisioni | Revisione e correzione |
| Dati sintetici | Testi delle descrizioni delle attività | Scelta di paesi e casi limite; revisione dei testi |
| Codice | Implementazione per fasi | Priorità, review dei diff, accettazione |
| Verifica | Scrittura di test ed eval | Definizione di cosa misurare e delle soglie di accettazione |

## Il workflow

1. **Formalizzare l'input.** La traccia è diventata un file Markdown nel repo (escluso da git), così l'agente lavora sempre sulla stessa fonte e non sulla mia memoria della conversazione.
2. **Esplorare prima di costruire.** Prima di scrivere codice ho chiesto all'AI di individuare le **sfide ingegneristiche**, con particolare attenzione all'integrazione dell'AI, e di presentare per ciascuna opzioni e trade-off: [`engineering-challenges.md`](engineering-challenges.md).
3. **Decidere io, una sfida alla volta.** Ho risposto punto per punto, spesso modificando la proposta. L'AI mi ha posto domande mirate sui punti in cui le mie scelte lasciavano ambiguità o rischi (vedi registro).
4. **Registrare le decisioni.** Ogni decisione è diventata un ADR in [`adr/`](adr/README.md), con le alternative scartate e le esclusioni motivate.
5. **Fissare il contesto per l'agente.** `CLAUDE.md` riassume principio guida, decisioni e vincoli. In questo modo ogni nuova sessione parte allineata, e una scelta ancora aperta non viene trattata come definitiva.
6. **Implementare per fasi** (ADR-0015): prima una slice end-to-end funzionante con il mock, poi gli strati in ordine di valore. Ogni fase si chiude con codice funzionante, rivisto e testato.
7. **Verificare.** Test, eval e validatore deterministico (vedi sotto).
8. **Parallelizzare quando le interfacce sono fissate.** Frontend e fixture del catalogo sono stati delegati a sotto-agenti, ciascuno con una cartella esclusiva e un contratto esplicito (tipi dell'API, schema dei fixture e vincoli da autoverificare). Nel frattempo l'agente principale scriveva il backend. Il contratto scritto prima è ciò che ha reso possibile lavorare in parallelo senza conflitti.

## Registro: dove ho corretto, integrato o accettato le proposte dell'AI

È la parte che ritengo più significativa: mostra dove il mio giudizio ha cambiato la proposta, e dove invece è stata l'AI a farmi notare un problema.

| Tema | Proposta dell'AI | Decisione finale | Chi ha spostato la decisione e perché |
|---|---|---|---|
| Requisiti mancanti nella traccia | Default ragionevoli (1 viaggiatore, 7 notti, partenza da Roma) | Tutti i campi obbligatori, a `null` finché non vengono raccolti, con **valori flessibili** (durata 5-7 giorni, "consigliami tu", "ovunque") | **Io**: i default silenziosi nascondono scelte che l'utente non ha fatto; i valori flessibili rispecchiano come si pianifica davvero un viaggio |
| "Consigliami tu" | — | L'LLM sceglie, ma solo tra i paesi che il codice ha verificato come fattibili | **AI**: affinamento della mia idea, per coerenza con il principio guida |
| Catena di fallback | Groq → Gemini → Ollama; mock separato per i test | **Gemini → Groq → LM Studio → Mock**, con il mock come ultimo anello | **Io**: Gemini è il mio piano A; il mock in catena garantisce che il sistema risponda sempre |
| Mock in produzione | L'AI ha segnalato il rischio di risposte finte senza che l'utente lo sappia | **Ogni risposta salvata con il provider che l'ha generata, con un tag visibile in chat** | **AI** ha posto il problema, **io** ho scelto la soluzione: trasparenza per messaggio invece di un banner generico |
| Planner | Greedy + K varianti, ILP in futuro | Solo greedy dietro un'interfaccia; poi **3 varianti**, su domanda dell'AI | **Io** ho ridotto lo scope; **l'AI** ha fatto notare che le varianti costano poco con lo stesso greedy |
| Memoria della conversazione | Opzioni (troncamento, riassunto, finestra); storico come opzionale | **Storico implementato + compaction automatica a soglia** | **Io**: ho alzato la priorità e definito il meccanismo |
| Osservabilità | Langfuse Cloud opzionale + tabella `llm_calls` propria | **Langfuse self-hosted** come fonte unica + **pagina Tracing nella UI** | **Io**: una sola fonte di verità per le metriche, e self-hosted perché il reviewer non ha le mie chiavi |
| Guardrail di dominio | — (non previsto nella prima analisi) | **Rifiuto delle richieste fuori scope**: verdetto nelle chiamate strutturate esistenti, testo del rifiuto fisso scritto dal codice (ADR-0016) | **Io**: requisito aggiunto; **l'AI** ha proposto il meccanismo a costo zero e il rifiuto non generato dall'LLM |
| Contenuti AI nella UI | — | **Ogni contenuto generato da AI è marcato** con l'icona delle stelline; il mock (regole) e il codice hanno marcature diverse | **Io**: requisito; **l'AI** ha proposto di distinguere AI, regole e codice e di esporre la provenienza come dato dell'API |
| Logging | — | **JSON su stdout**, eventi dal nome stabile, nessun contenuto dei messaggi; separato da trace LLM e audit (ADR-0017) | **Io**: scelta della destinazione dei log; **l'AI** ha proposto la separazione in tre canali |
| Identificatori | Id interi per voli e righe d'itinerario, slug per hotel e attività | **Tutti gli id sono UUID**, deterministici per il catalogo (seed riproducibile) e casuali a runtime | **Io**: requisito; **l'AI** ha proposto gli UUID deterministici per non perdere la riproducibilità del seed |
| Tool calling | Due opzioni: azioni strutturate estese o tool calling nativo | **Tool calling nativo**, loop limitato, l'LLM non vede mai un id | **Io**: scelta del nativo; **l'AI** ha proposto i vincoli di sicurezza (niente id, tool terminali, nuovo itinerario validato) |
| Eliminazione delle conversazioni | — | Cancellazione reale di messaggi e proposte; resta solo il minimo necessario alle prenotazioni confermate | **Io**: requisito; **l'AI** ha segnalato il vincolo delle prenotazioni |
| Streaming | SSE o WebSocket | **SSE** | **Io**: WebSocket è eccessivo per una comunicazione unidirezionale |
| Multimodalità | Opzionale, con due approcci possibili | **Esclusa** | **Io**: non rafforza il nucleo e aggiunge superficie di attacco |
| Message broker | (proposto da me) | **Escluso e documentato** | **L'AI** l'ha sconsigliato come over-engineering; **io** ho accettato, chiedendo di motivare tutte le esclusioni |
| Autenticazione | (proposto da me: Keycloak, Google o entrambi) L'AI ha proposto Keycloak con login Google federato, spento di default | **Solo Keycloak** | **Io**: il login Google non aggiunge valore al nucleo e richiede segreti; il backend dipende solo da OIDC, quindi resta aggiungibile |
| Abbonamento Claude a runtime | (domanda mia) | Usato solo per lo sviluppo | **AI**: chiarimento sui termini d'uso, che ho verificato |
| Scope vs tempo disponibile | L'AI ha segnalato il rischio di un backlog troppo ampio | **Slice end-to-end prima**, poi strati in ordine di valore | Decisione condivisa (ADR-0015) |
| Persistenza | SQLite all'inizio; Postgres dopo la scelta di Langfuse self-hosted | **PostgreSQL** (ADR-0014) | **AI**: una decisione successiva ha cambiato i presupposti di una precedente; **io** ho confermato |
| Database dei test | In implementazione l'AI ha fatto girare i test su SQLite (Docker era spento), annotandolo solo come deviazione | **Test su PostgreSQL**, con container usa-e-getta e migrazioni reali | **Io**: una decisione accettata in un ADR non si cambia in silenzio; l'AI deve chiedere prima di deviare |

## Come verifico l'output dell'AI

- **Codice:** leggo ogni diff prima di accettarlo. I test unitari e di integrazione girano in CI sul provider mock. L'agente non fa commit senza la mia richiesta.
- **Correttezza dei vincoli:** il validatore deterministico (ADR-0003) controlla ogni itinerario, quindi un bug introdotto dall'AI nel planner viene intercettato.
- **Comportamento LLM:** golden set e metriche (ADR-0008). Le modifiche ai prompt si confrontano sui numeri, non a impressione.
- **Affermazioni fattuali:** limiti dei free tier, supporto all'output strutturato e API dei provider li verifico sulla documentazione ufficiale. Negli ADR i punti non ancora verificati sono marcati **"Da verificare"**.
- **Testi generati** (descrizioni delle attività): riletti e corretti prima di essere versionati.

## Errori dell'AI intercettati

Casi reali emersi durante l'implementazione. Nessuno è stato trovato rileggendo il codice: li hanno fatti emergere test ed esecuzioni di prova, ed è per questo che test e smoke test fanno parte del workflow.

| Errore | Come è emerso | Correzione |
|---|---|---|
| Le radici delle categorie venivano cercate come sottostringhe: "p**arte**nza" faceva scattare la categoria *cultura* | Smoke test dell'estrazione su frasi reali | Corrispondenza solo a inizio parola |
| "in due settimane" letto come "2 viaggiatori" | Smoke test dell'estrazione | Esclusione esplicita quando "due" è seguito da un'unità di tempo |
| Durante un refactoring l'agente ha cancellato per errore la regola "viaggio da solo/a" | Unit test parametrizzato | Regola ripristinata; il test resta come protezione |
| Prima versione del planner con un ricalcolo della riserva di budget troppo costoso (migliaia di combinazioni × giorni² × attività²) | Analisi della complessità prima di eseguirlo | Dati per combinazione condivisi tra le 3 varianti e riserva aggiornata in O(1) per candidato |
| Il costo minimo stimato ignorava che le attività devono essere distinte e sottostimava il costo | Unit test con budget esattamente pari al minimo | Stima con attività distinte |
| Con "agosto" tutte le varianti partivano il 31 agosto (settembre costa meno): corretto per il codice, assurdo per l'utente | Esecuzione end-to-end di una conversazione | Il viaggio si svolge nel mese quando possibile; assunzione documentata |
| Il file di migrazione generato conteneva una data, in contrasto con una regola di progetto | Controllo dei file generati | Data rimossa dal file e dal template |
| Lo schema JSON dell'output veniva inviato tre volte per ogni chiamata (circa 1.800 token) | Benchmark con le chiavi reali: Groq ha risposto 429 dopo una sola chiamata | Schema inviato una sola volta, e nel prompt solo se il provider non supporta `json_schema` |
| Un modello ritirato (404) veniva trattato come "formato non supportato", scalando i formati inutilmente | Prova con la chiave Gemini reale | Il 404 rende il provider non disponibile, con cooldown |
| Con un LLM reale la risposta a "chiedi l'aeroporto di partenza" era «Buongiorno!», e le varianti venivano chiamate "economy/balanced" | Conversazioni di prova con Gemini | Prompt di scrittura riformulato, etichette italiane nei dati passati al modello |
| Gemini falliva sempre al secondo passo del loop di tool, e il fallback su Groq lo nascondeva | Log `llm.provider_failed` e riproduzione diretta della chiamata | La `thought_signature` di Gemini 3 viene rimandata allo stesso provider |
| Dopo una modifica il modello scriveva «il totale rimane» con un totale diverso, e presentava il nuovo hotel come quello "già" previsto | Conversazioni di prova con il tool calling | I risultati dei tool riportano anche il valore precedente (attività, hotel, totale) |



| Rischio | Mitigazione |
|---|---|
| **Over-engineering** (l'AI tende a proporre "tutto") | Prioritizzazione esplicita ed esclusioni motivate (ADR-0015) |
| **Allucinazioni** su API, limiti e prezzi | Verifica sulle fonti; marcatura "Da verificare" |
| **Deriva dal design** tra una sessione e l'altra | `CLAUDE.md` + ADR come contesto versionato |
| **Fiducia eccessiva** nel codice generato | Review dei diff, test, validatore, eval |
| **Sicurezza** | Nessun segreto nel contesto dell'agente; `.env` escluso da git |

## Context engineering: gli artefatti

- [`CLAUDE.md`](../CLAUDE.md): istruzioni di progetto per l'agente (principio guida, decisioni, vincoli, lingua dei documenti).
- [`engineering-challenges.md`](engineering-challenges.md): analisi delle sfide e decisioni.
- [`adr/`](adr/README.md): le decisioni, una per file.
- Commit con il trailer `Co-Authored-By` quando il contributo dell'agente è sostanziale, per avere tracciabilità nella history git.


## Da completare a fine progetto

- Quanta parte del codice è stata generata e quanta modificata a mano.
- Cosa rifarei diversamente nel modo di usare l'AI.
