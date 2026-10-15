# ADR-0003 — Planner greedy sostituibile, 3 varianti, validatore deterministico

- **Stato:** Accettata (estesa da [ADR-0022](0022-varianti-con-budget-illimitato-e-ovunque.md) per «ovunque»; regola «un'attività per ogni giorno» modificata da [ADR-0023](0023-giorni-di-viaggio.md))
- **Riferimenti:** [engineering-challenges §A3](../engineering-challenges.md#a3-generazione-dellitinerario--adr-0003)

## Contesto

Un itinerario è composto da volo A/R + hotel per ogni notte + un'attività per ogni giorno, con il vincolo:

```text
costo_voli × viaggiatori + Σ prezzo_notte × camere + Σ costo_attività × viaggiatori ≤ budget
```

Vanno rispettate le disponibilità per data e massimizzata l'aderenza alle preferenze. È una variante di un knapsack multi-vincolo. La flessibilità di date e durata (ADR-0002) moltiplica le combinazioni, che restano comunque poche: al massimo circa 31 date di partenza × 13 durate per paese.

## Opzioni considerate

1. **Greedy/euristico**.
2. **Solver ILP** (OR-Tools / PuLP).
3. **Generazione dell'itinerario da parte dell'LLM**: scartata già in ADR-0001.

## Decisione

- **Interfaccia `Planner`** con un'implementazione `GreedyPlanner`, sostituibile senza toccare il resto del sistema.
- **Ricerca su due livelli:**
  1. combinazioni (data di partenza nel mese × durata nell'intervallo × paese candidato), esplorate in modo esaustivo con potatura (es. si scarta la combinazione se volo + notti minime superano già il budget);
  2. scelta degli elementi dentro ogni combinazione, in modo greedy.
- **3 varianti** dallo stesso algoritmo con strategie di scelta diverse:
  - **economica**: costo minimo;
  - **bilanciata**: miglior rapporto tra score delle preferenze e costo;
  - **premium**: score massimo entro il budget.
- **Score delle attività**: similarità semantica dal RAG (ADR-0004) + match di categoria + target. Ogni giorno ha un'attività diversa.
- **Validatore deterministico** separato dal planner: ricontrolla budget, disponibilità e ID di ogni itinerario prima che arrivi all'utente. Il planner potrebbe avere un bug; il validatore è la seconda linea.
- **Infeasibility**: se nessuna combinazione è fattibile, il planner restituisce i **vincoli che bloccano** e i **rilassamenti possibili** (meno giorni, altro mese, altro paese, budget minimo necessario), che l'LLM presenta all'utente.

## Motivazione

- Il greedy è spiegabile, veloce e sufficiente su un catalogo piccolo.
- L'interfaccia rende la decisione **reversibile**: un ILP si può introdurre più avanti, se gli eval mostrano itinerari peggiori del necessario.
- Le 3 varianti costano poco codice e trasformano la proposta in una scelta naturale in chat.
- Restituire vincoli bloccanti e rilassamenti trasforma un fallimento in un passo della conversazione.

## Conseguenze

- **Positive:** risultato riproducibile, completamente testabile, nessun costo LLM per la pianificazione.
- **Negative:** il greedy può perdere l'ottimo globale (es. un hotel più caro che libera attività migliori). Accettato per questo perimetro.
- **Evoluzione:** `IlpPlanner` dietro la stessa interfaccia, confrontato con il greedy sugli eval.
