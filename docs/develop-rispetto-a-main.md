# `develop` rispetto a `main`: cosa è cambiato e perché

`main` contiene la consegna con le fasi 1-3 di [ADR-0015](adr/0015-perimetro-priorita-esclusioni.md): slice end-to-end, LLM reali con fallback e streaming, osservabilità con Langfuse. `develop` parte da lì e aggiunge il lavoro nato **provando l'app da utente con gli LLM reali**.

Quasi ogni modifica viene da un problema osservato in una conversazione vera, non da una funzionalità pianificata in anticipo. Per questo ognuna qui sotto indica il caso che l'ha fatta emergere. Le trascrizioni e la loro verifica sono in [conversazioni-reali.md](conversazioni-reali.md).

## Come provarla

```bash
git checkout develop
cd project
docker compose up --build
```

Gli utenti `demo` e `reviewer` trovano sei conversazioni registrate con Groq e Gemini, ricaricate dal seed senza chiamare nessun LLM. pgweb, in sola lettura su <http://localhost:8081>, permette di controllare prenotazioni e inventario.

## Le modifiche

### 1. Date esatte spiegate, errori dei tool non più visibili

- **Caso:** «voglio partire esattamente il 4 febbraio» produceva in chat il messaggio interno destinato all'LLM («chiedi all'utente di specificarlo»), ripetuto due volte.
- **Cosa:** il codice riconosce una data esatta e risponde con una nota fissa (si sceglie solo il mese, [ADR-0002](adr/0002-requisiti-strutturati-valori-flessibili.md)). Gli errori dei tool hanno un testo per l'LLM e uno, separato, che può arrivare all'utente.

### 2. UI del database in sola lettura (pgweb)

- **Perché:** il reviewer deve poter verificare ciò che gli ADR promettono: inventario che scende e risale, snapshot dei prezzi, idempotenza.
- **Cosa:** pgweb su `:8081`, con due protezioni: un ruolo PostgreSQL che ha solo il permesso di lettura e la sessione read-only di pgweb.

### 3. Valori «qualsiasi» per budget, preferenze e partenza ([ADR-0021](adr/0021-valori-qualsiasi-espliciti.md))

- **Perché:** «i soldi non sono un problema», «parto da qualsiasi aeroporto» e «non ho preferenze» sono risposte legittime, ma ADR-0002 non le prevedeva.
- **Cosa:** `budget_total = "unlimited"`, `departure_airport = "ANY"`, `categories = []`. Il codice li accetta solo se nel messaggio dell'utente c'è un'espressione esplicita: un LLM che usa «qualsiasi» per riempire un dato mancante sarebbe un default silenzioso. Mese e durata restano senza «qualsiasi», per scelta.

### 4. Varianti distinte con budget illimitato e «ovunque» ([ADR-0022](adr/0022-varianti-con-budget-illimitato-e-ovunque.md))

- **Caso:** con budget illimitato e «ovunque», economica e bilanciata costavano 645 € e 646 €, e tutte e tre le varianti erano in Sicilia.
- **Cosa:**
  - senza budget, il prezzo si pesa rispetto al costo della premium;
  - con «ovunque», ogni variante va in un paese diverso quando possibile;
  - le scelte fatte per conto dell'utente arrivano alla risposta come frasi scritte dal codice.

### 5. Note sulle preferenze validate da Pydantic

- **Caso:** il pannello mostrava «Cultura, Relax · Grecia a giugno, 5 giorni, da Roma…», perché il mock copiava l'intero messaggio nelle note. Le note entrano anche nella query semantica del RAG.
- **Cosa:**
  - `description` e `max_length` nello schema inviato all'LLM;
  - un validatore che **ripulisce senza rifiutare**: toglie budget, date e numero di persone, e scarta gusti non presenti nel messaggio dell'utente;
  - la scelta di ripulire invece di rifiutare è un trade-off dichiarato: le note pesano solo sull'ordinamento, quindi un rifiuto costerebbe un nuovo tentativo o l'intera estrazione.

### 6. Fallback tra provider a metà del ciclo dei tool

- **Caso:** Groq andava in rate limit dopo il primo tool. Gemini rifiutava le chiamate a funzione prodotte da Groq, perché senza la sua `thought_signature`, e la catena finiva sul mock.
- **Cosa:** la cronologia dei tool prodotta da un altro provider viene riproposta come testo; quella dello stesso provider resta nativa.

### 7. Giorni di viaggio ([ADR-0023](adr/0023-giorni-di-viaggio.md))

- **Caso:** street food a Tokyo il primo giorno con arrivo all'01:25 del giorno dopo: un'attività pagata e impossibile.
- **Cosa:**
  - si preferiscono voli che lasciano tempo per un'attività;
  - se non ce ne sono, il primo o l'ultimo giorno diventa un giorno di viaggio dichiarato;
  - il validatore rifiuta le attività che non entrano negli orari.
- **Deviazione dalla traccia:** è una deviazione voluta da «un'attività ogni giorno», scelta tra tre opzioni e limitata ai casi senza voli compatibili.

### 8. L'annullamento riapre la conversazione ([ADR-0024](adr/0024-annullamento-riapre-la-conversazione.md))

- **Caso:** dopo un annullamento la chat restava «prenotata» e a un nuovo messaggio rispondeva «questo viaggio è già prenotato».
- **Cosa:** si torna alle proposte rimaste, oppure alla raccolta dei requisiti, con un messaggio fisso.

### 9. Verifiche deterministiche sul testo dell'LLM ([ADR-0025](adr/0025-verifiche-deterministiche-sul-testo-llm.md))

- **Casi:**
  - l'LLM aveva 1963 € nei dati e ha scritto «1 966 €»;
  - a una domanda sulle terme ha inventato «saune e massaggi»;
  - a «prenota tu la bilanciata» non ha selezionato la variante, e il pulsante di conferma non compariva.
- **Cosa:**
  - ogni importo scritto dall'LLM deve essere fra quelli calcolati dal codice, altrimenti la risposta viene sostituita;
  - la ricerca delle attività mette prima quelle nominate nella domanda;
  - «nel catalogo non è indicato» quando un dettaglio manca;
  - una scelta esplicita seleziona la variante anche se l'LLM risponde solo a parole (mai la prenotazione, che resta un pulsante);
  - le etichette interne ripetute dal modello vengono tolte.

### 10. Pubblico di riferimento delle attività

- **Caso:** una serata «per giovani» in un viaggio tranquillo di coppia; una lezione di paddle surf per una famiglia con bambini.
- **Cosa:** il pubblico (coppie, famiglie, senior, solo), ricavato da note e viaggiatori, dà un piccolo bonus nel punteggio del planner, nelle sostituzioni e nella ricerca.

### 11. Chat precaricate registrate con gli LLM reali

- **Perché:** le chat generate dal mock non dicono nulla sulla qualità dei modelli veri.
- **Cosa:**
  - le conversazioni sono fatte via API da un tester che si comporta da utente, verificate contro il database da revisori indipendenti e poi esportate in un fixture;
  - il seed le ricarica con id nuovi;
  - una prenotazione ricaricata riprende l'inventario tutto o niente, e se non può viene marcata, così annullarla non restituisce nulla;
  - le risposte imperfette restano nelle trascrizioni, perché sono parte dell'analisi.

### 12. Tool di sola lettura sul catalogo ([ADR-0026](adr/0026-tool-di-sola-lettura-sul-catalogo.md))

- **Caso:** «mi dici quali sono le destinazioni disponibili?» riceveva il rifiuto fisso, perché nella raccolta dei requisiti non c'era modo di consultare il catalogo.
- **Cosa:**
  - `list_destinations`, `list_departure_airports`, `get_hotels`, `search_activities` e `check_availability` (disponibilità reale per mese), in tutte le fasi;
  - l'estrazione segnala la domanda: i requisiti dello stesso messaggio vengono registrati comunque e la risposta chiede quelli mancanti.

## Come è stato verificato

- **Test:** 116 test (erano 87 su `main`), ognuno dei difetti trovati in revisione con un test di regressione.
- **Revisione del codice:** quattro revisori per area e uno scettico per area hanno confermato 21 difetti nelle modifiche, tutti corretti.
- **Conversazioni:** ogni affermazione delle risposte LLM è stata confrontata con il database da un revisore, e un secondo ha provato a confutare ogni segnalazione.
- **Avvio da zero:** in un progetto Docker separato, come lo fa il reviewer.

Il risultato più importante è anche il più semplice da enunciare. In tutte le conversazioni **non c'è nessun errore in ciò che decide il codice**: totali, budget, date, disponibilità, prenotazioni, inventario. I difetti rimasti sono tutti nel testo libero dei modelli, e sono elencati nei [miglioramenti futuri](../README.md#miglioramenti-futuri).
