# ADR-0001 — Controllo ibrido: state machine + tool calling dentro le fasi

- **Stato:** Accettata (transizione dopo l'annullamento aggiunta da [ADR-0024](0024-annullamento-riapre-la-conversazione.md); tool di sola lettura sul catalogo in tutte le fasi da [ADR-0026](0026-tool-di-sola-lettura-sul-catalogo.md))
- **Riferimenti:** [engineering-challenges §A1](../engineering-challenges.md#a1-ruolo-dellllm-nellarchitettura--adr-0001)

## Contesto

L'assistente deve condurre una conversazione naturale, ma anche produrre itinerari che rispettano vincoli rigidi (budget, disponibilità) e compiere un'azione con effetti reali (la prenotazione). Bisogna decidere quanto controllo dare all'LLM sul flusso.

I provider disponibili sono free tier con modelli di capacità variabile, e il sistema deve funzionare anche con un mock deterministico (ADR-0005).

## Opzioni considerate

1. **End-to-end**: l'LLM riceve il catalogo e scrive l'itinerario.
2. **Agente libero con tool calling**: l'LLM sceglie quali tool chiamare e in che ordine, prenotazione compresa.
3. **Workflow rigido**: il backend guida tutto e l'LLM fa solo estrazione e generazione del testo.
4. **Ibrido**: una state machine per le fasi di alto livello, con tool calling solo dentro la fase corrente.

## Decisione

Opzione 4. Il backend mantiene una **state machine esplicita** con le fasi:

```text
COLLECTING_REQUIREMENTS → PROPOSING → AWAITING_CONFIRMATION → BOOKED
          ↑                    │
          └── modifica requisiti ┘
```

- Le **transizioni** le decide il codice, in base allo stato strutturato (es. si passa a `PROPOSING` solo quando tutti i requisiti sono valorizzati, ADR-0002).
- **Dentro una fase** l'LLM ha a disposizione solo i tool di quella fase (es. in `PROPOSING`: cercare attività alternative o chiedere una variante diversa).
- L'itinerario lo costruisce il **planner deterministico** (ADR-0003). L'LLM lo presenta e lo argomenta.
- Il passaggio a `BOOKED` avviene **solo** tramite conferma esplicita dell'utente (ADR-0006), mai su iniziativa del modello.

## Motivazione

- Le transizioni critiche non dipendono dal comportamento del modello: è il principio guida applicato al flusso.
- Ogni fase ha input e output definiti, quindi si testa e si valuta separatamente (ADR-0008).
- L'insieme ridotto di tool per fase rende il tool calling affidabile anche con modelli piccoli, e il mock lo può riprodurre.
- La conversazione resta naturale dentro ogni fase, cosa che un workflow rigido non garantirebbe.

Le opzioni 1 e 2 sono state scartate perché lasciano al modello garanzie che deve dare il codice: correttezza del budget, esistenza degli elementi, avvio della prenotazione.

## Conseguenze

- **Positive:** comportamento prevedibile e testabile, superficie di attacco ridotta (ADR-0007), meno token per turno.
- **Negative:** le richieste fuori percorso (es. una domanda generica sul paese durante la conferma) vanno gestite esplicitamente con una risposta libera che non cambia fase.
- **Da verificare:** che i modelli free tier gestiscano bene la scelta tra "aggiornare i requisiti" e "rispondere e basta" nella stessa fase.
