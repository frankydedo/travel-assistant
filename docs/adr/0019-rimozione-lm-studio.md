# ADR-0019 — Rimozione di LM Studio dalla catena

- **Stato:** Accettata (modifica la catena di [ADR-0005](0005-provider-llm-catena-fallback.md) e [ADR-0018](0018-ordine-catena-groq-prima.md))

## Contesto

ADR-0005 prevedeva LM Studio in locale come terzo anello della catena, dopo i provider cloud e prima del mock. Con l'implementazione e le prove reali sono emersi tre fatti:

- LM Studio richiede software installato e un modello scaricato in locale, quindi il reviewer che avvia il progetto con `docker compose up` di fatto non lo usa;
- l'affidabilità è già coperta da due provider cloud indipendenti (Groq e Gemini) e dal mock deterministico, che risponde sempre;
- supportarlo costava codice dedicato (scoperta del modello caricato, provider senza chiave, accesso all'host da Docker) che nessuno avrebbe esercitato.

## Decisione

- La catena diventa **Groq → Gemini → Mock**.
- Il codice specifico per LM Studio viene rimosso: configurazione, scoperta del modello, accesso all'host da Docker e tag `LMSTUDIO`.
- L'adapter resta generico sull'API OpenAI-compatibile: aggiungere un provider locale o un altro provider cloud richiede solo una voce nel registro dei provider.

## Motivazione

Ogni componente che nessuno esercita è codice da mantenere e da testare senza un beneficio reale. Il valore che LM Studio doveva portare (rispondere senza quote esterne) lo dà già il mock come ultimo anello.

## Conseguenze

- **Positive:** catena più semplice, meno configurazione, nessuna dipendenza dall'host nel compose.
- **Negative:** nessun LLM "vero" disponibile senza chiavi; in quel caso risponde il mock, segnalato in chat.
