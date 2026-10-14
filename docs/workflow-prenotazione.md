# Workflow di prenotazione

Questo documento visualizza il percorso completo, dalla prima frase dell'utente alla prenotazione confermata, con tutti gli attori coinvolti. Le decisioni dietro ogni passaggio sono negli ADR: [0001](adr/0001-controllo-ibrido-state-machine.md) (controllo ibrido), [0002](adr/0002-requisiti-strutturati-valori-flessibili.md) (requisiti), [0003](adr/0003-planner-greedy-tre-varianti.md) (planner e validatore), [0005](adr/0005-provider-llm-catena-fallback.md) (provider), [0006](adr/0006-prenotazione-sicura.md) (prenotazione), [0007](adr/0007-guardrail-sicurezza-ai.md) (guardrail).

## Gli attori

| Attore | Natura | Ruolo |
|---|---|---|
| **Utente** | umano | Esprime le esigenze e **conferma esplicitamente** la prenotazione (human in the loop) |
| **Frontend** | React | Chat, card degli itinerari, pulsante di conferma, dashboard |
| **Keycloak** | identity provider | Autentica l'utente e rilascia il JWT |
| **Orchestratore** | codice deterministico | State machine delle fasi: decide le transizioni, valida ed esegue i tool, chiama planner e validatore |
| **Interprete LLM** | probabilistico | Comprende il linguaggio (estrae i requisiti) e spiega i risultati (domande, presentazione delle varianti). Può **proporre** tool call, non eseguirle |
| **Gateway LLM** | codice deterministico | Catena di fallback Groq → Gemini → Mock, con cooldown; registra il provider di ogni risposta |
| **Tool di fase** | codice deterministico | Operazioni disponibili all'Interprete nella fase corrente, con argomenti validati da schema |
| **RAG (Chroma)** | indice vettoriale | Ordina le attività per pertinenza alle preferenze, con filtro obbligatorio su paese e mese |
| **Planner** | codice deterministico | Costruisce 3 varianti di itinerario (greedy) |
| **Validatore** | codice deterministico | Verifica budget, disponibilità e ID di ogni itinerario: seconda linea di difesa dopo il planner |
| **Servizio prenotazioni** | codice deterministico | Transazione unica, decremento atomico dell'inventario, idempotenza, snapshot dei prezzi |
| **PostgreSQL** | DB relazionale | Fonte di verità per catalogo, inventario, itinerari e prenotazioni |
| **Langfuse** | osservabilità | Trace di ogni turno e di ogni chiamata LLM |

### Perché "Interprete" e non "agente"

Un agente decide autonomamente quali azioni compiere e in che ordine. Qui non è così:

- il **flusso** lo decide l'orchestratore;
- gli **itinerari** li costruisce il planner;
- la **prenotazione** la avvia solo l'utente.

Il modello fa due cose: **interpreta** il linguaggio naturale in dati strutturati e **spiega** i risultati del codice in linguaggio naturale. Il nome segue il principio guida: *l'LLM capisce e spiega, il codice decide e garantisce.*

## 1. Vista d'insieme: zone di fiducia

La linea che conta è il confine tra la zona probabilistica e quella deterministica. Tutto ciò che attraversa il confine verso il codice viene validato, e **non esiste alcun collegamento tra l'Interprete e il servizio prenotazioni**.

```mermaid
flowchart LR
    U(["👤 Utente"])

    subgraph FE["Frontend React"]
        CHAT["Chat<br/>card itinerari<br/>tag provider"]
        BTN["Pulsante<br/>Conferma e prenota<br/>(human in the loop)"]
        DASH["Dashboard<br/>prenotazioni"]
    end

    KC["🔐 Keycloak<br/>OIDC · JWT"]

    subgraph PROB["Zona probabilistica: l'LLM capisce e spiega"]
        INT["🧠 Interprete LLM<br/>estrae requisiti · spiega risultati<br/>propone tool call"]
    end

    subgraph DET["Zona deterministica: il codice decide e garantisce"]
        ORCH["⚙️ Orchestratore<br/>state machine delle fasi"]
        GW["Gateway LLM<br/>Groq → Gemini → Mock<br/>cooldown · tag provider"]
        TOOLS["🔧 Tool di fase<br/>schema Pydantic · ID verificati"]
        RAG[("Chroma<br/>RAG attività")]
        PLAN["Planner greedy<br/>3 varianti"]
        VAL["✅ Validatore<br/>budget · disponibilità · ID"]
        BOOK["🔒 Servizio prenotazioni<br/>transazione · idempotenza<br/>snapshot prezzi"]
        DB[("PostgreSQL<br/>catalogo · inventario<br/>itinerari · prenotazioni")]
    end

    LF["📈 Langfuse<br/>trace · costi"]

    U --> CHAT
    U --> BTN
    KC -. "JWT" .-> FE
    CHAT -- "messaggio + JWT" --> ORCH
    ORCH -- "SSE: testo · card · progress" --> CHAT

    ORCH -- "stato + messaggio" --> GW
    GW --> INT
    INT -- "JSON strutturato<br/>o proposta di tool call" --> GW
    GW -- "risposta + provider" --> ORCH

    ORCH -- "valida ed esegue" --> TOOLS
    TOOLS --> RAG
    TOOLS --> PLAN
    ORCH --> RAG
    ORCH --> PLAN
    PLAN --> DB
    PLAN --> VAL
    VAL -- "solo itinerari validi<br/>o rilassamenti" --> ORCH
    ORCH -- "itinerari proposed" --> DB

    BTN -- "itinerary_id + idempotency key + JWT" --> BOOK
    BOOK -- "transazione" --> DB
    BOOK -- "esito" --> DASH

    ORCH -. "trace" .-> LF
    GW -. "generation" .-> LF

    NOTE["⛔ L'Interprete non ha tool di prenotazione<br/>e non vede mai user_id o prezzi modificabili"]
    INT ~~~ NOTE

    classDef prob fill:#fff4e5,stroke:#e8a33d,color:#000
    classDef det fill:#e8f1ff,stroke:#3d7be8,color:#000
    classDef hitl fill:#e9f9ee,stroke:#2f9e57,color:#000,stroke-width:2px
    classDef warn fill:#fdecec,stroke:#d64545,color:#000
    class INT prob
    class ORCH,GW,TOOLS,PLAN,VAL,BOOK det
    class BTN hitl
    class NOTE warn
```

## 2. Le fasi della conversazione

Le transizioni le decide l'orchestratore, in base allo stato strutturato, non al testo dell'LLM.

```mermaid
stateDiagram-v2
    state "Raccolta requisiti<br/>COLLECTING_REQUIREMENTS" as COLLECTING
    state "Proposta<br/>PROPOSING" as PROPOSING
    state "Attesa conferma<br/>AWAITING_CONFIRMATION" as AWAITING
    state "Prenotato<br/>BOOKED" as BOOKED

    [*] --> COLLECTING
    COLLECTING --> COLLECTING : almeno un campo è null
    COLLECTING --> PROPOSING : tutti i campi valorizzati e validi
    PROPOSING --> COLLECTING : l'utente cambia i requisiti o accetta un rilassamento
    PROPOSING --> PROPOSING : modifica di una variante via tool
    PROPOSING --> AWAITING : l'utente sceglie una variante
    AWAITING --> PROPOSING : ci ripensa o la disponibilità è cambiata
    AWAITING --> COLLECTING : cambia un requisito e il nuovo valore non è valido o non è fattibile
    AWAITING --> BOOKED : clic su Conferma e prenota e transazione riuscita
    BOOKED --> [*]
```

## 3. Sequenza completa

I nomi dei tool sono indicativi: verranno fissati in implementazione.

```mermaid
sequenceDiagram
    autonumber
    actor U as Utente
    participant FE as Frontend
    participant KC as Keycloak
    participant OR as Orchestratore
    participant LLM as Interprete LLM (via Gateway)
    participant T as Tool di fase
    participant R as RAG (Chroma)
    participant P as Planner
    participant V as Validatore
    participant BK as Servizio prenotazioni
    participant DB as PostgreSQL

    U->>FE: accede
    FE->>KC: OIDC Authorization Code + PKCE
    KC-->>FE: JWT

    rect rgba(61, 123, 232, 0.08)
    Note over U,DB: Fase 1 · Raccolta requisiti
    loop finché un campo di TripRequirements è null
        U->>FE: messaggio in linguaggio naturale
        FE->>OR: POST /chat con JWT, risposta in SSE
        OR->>OR: valida JWT, rate limit, carica lo stato
        OR->>LLM: messaggio + stato + schema dei requisiti
        Note right of LLM: fallback Groq → Gemini → Mock
        LLM-->>OR: aggiornamento parziale in JSON
        OR->>OR: validazione Pydantic e merge nello stato
        OR->>LLM: formula la domanda sui campi mancanti
        LLM-->>OR: testo
        OR-->>FE: SSE token + done con provider
        FE-->>U: risposta con tag GROQ / GEMINI / MOCK
    end
    end

    rect rgba(47, 158, 87, 0.08)
    Note over U,DB: Fase 2 · Proposta
    OR-->>FE: SSE progress cerco voli, hotel e attività
    OR->>R: preferenze con filtro su paese e mese
    R-->>OR: attività ordinate per pertinenza
    OR->>P: requisiti + score delle attività
    P->>DB: voli, hotel e disponibilità per data
    P-->>OR: 3 varianti candidate
    OR->>V: verifica budget, disponibilità e ID
    alt nessuna variante valida
        V-->>OR: vincoli bloccanti + rilassamenti possibili
        OR->>LLM: spiega i rilassamenti
        LLM-->>OR: testo
        OR-->>FE: proposta di rilassamento
        Note over U,OR: se accettato si torna alla Fase 1 con i requisiti aggiornati
    else varianti valide
        V-->>OR: ok
        OR->>DB: salva gli itinerari in stato proposed
        OR->>LLM: presenta le varianti, solo con dati già validati
        LLM-->>OR: testo esplicativo
        OR-->>FE: SSE itinerary in JSON + testo
        FE-->>U: 3 card con prezzi calcolati dal server
    end

    opt modifica in chat
        U->>FE: per il giorno 3 vorrei qualcosa di più rilassante
        FE->>OR: messaggio
        OR->>LLM: messaggio + tool disponibili nella fase
        LLM-->>OR: proposta di tool call swap_activity
        OR->>T: valida schema e ID, poi esegue
        T->>R: attività alternative
        T->>P: ricalcola la variante
        P->>V: valida
        V-->>OR: ok
        OR-->>FE: card aggiornata
    end
    end

    rect rgba(232, 163, 61, 0.10)
    Note over U,DB: Fase 3 · Conferma (human in the loop)
    U->>FE: sceglie la variante bilanciata
    FE->>OR: selezione di itinerary_id
    OR-->>FE: riepilogo con prezzo finale + pulsante
    Note over LLM: l'Interprete non ha alcun tool di prenotazione
    U->>FE: clic su Conferma e prenota
    end

    rect rgba(214, 69, 69, 0.08)
    Note over U,DB: Fase 4 · Prenotazione
    FE->>BK: POST /bookings con itinerary_id, idempotency key e JWT
    BK->>BK: user_id letto dal JWT, mai dal client o dall'LLM
    BK->>DB: BEGIN
    BK->>DB: ricontrollo disponibilità e decremento condizionale
    alt inventario sufficiente
        BK->>DB: snapshot prezzi, stato confirmed, COMMIT
        BK-->>FE: 201 prenotazione confermata
        FE-->>U: conferma e dashboard aggiornata
    else disponibilità cambiata nel frattempo
        BK->>DB: ROLLBACK
        BK-->>FE: 409 conflitto
        FE->>OR: richiede nuove varianti
        Note over OR,P: si torna alla Fase 2
    end
    Note over FE,BK: un retry con la stessa idempotency key restituisce la stessa prenotazione
    end
```

## Dove intervengono i controlli

| Rischio | Dove viene fermato |
|---|---|
| L'LLM inventa un prezzo o un hotel | Il planner usa solo dati del DB; il validatore ricontrolla; le card mostrano i prezzi del server |
| L'LLM "decide" di prenotare | Non esiste un tool di prenotazione; serve il clic dell'utente |
| Prompt injection ("prenota gratis per un altro utente") | `user_id` dal JWT, prezzi dal DB, tool validati da schema |
| Doppio click o retry | Idempotency key |
| Due utenti sull'ultima camera | Decremento condizionale nella transazione → 409 e nuovo piano |
| Provider in quota | Gateway con fallback e cooldown; il tag mostra chi ha risposto |
| Domanda fuori ambito o tentativo di jailbreak ("scrivimi una poesia", "ignora le istruzioni") | Verdetto di scope nell'output strutturato; rifiuto con testo fisso scritto dal codice, stato invariato (ADR-0016) |
