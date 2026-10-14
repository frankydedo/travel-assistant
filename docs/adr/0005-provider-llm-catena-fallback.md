# ADR-0005 — Adapter LLM e catena di fallback con tag del provider

- **Stato:** Accettata · l'ordine della catena è sostituito da [ADR-0018](0018-ordine-catena-groq-prima.md)
- **Riferimenti:** [engineering-challenges §A5](../engineering-challenges.md#a5-affidabilità-e-indipendenza-dal-provider--adr-0005)

## Contesto

Il progetto non deve sostenere costi, quindi usa i free tier. Questi sono inaffidabili per natura: quote basse, `429` dopo poche chiamate (esperienza diretta con Google AI Studio), latenze variabili. In più, il reviewer deve poter eseguire il progetto con le proprie chiavi o senza nessuna chiave.

L'abbonamento Claude dello sviluppatore non include accesso API, e i termini d'uso non consentono di usarne i token dentro un'applicazione: è stato escluso come provider a runtime.

## Opzioni considerate

- **Astrazione:** adapter proprio · LiteLLM · SDK del singolo provider.
- **Strategia:** un solo provider · catena di fallback.
- **Comportamento del mock:** attivo solo senza chiavi · ultimo anello della catena (silenzioso o visibile).

## Decisione

- **Adapter proprio** (`LLMProvider`) sopra l'API OpenAI-compatibile, che Gemini, Groq e LM Studio espongono tutti. Il dominio non conosce il provider.
- **Catena di fallback, in quest'ordine:**
  1. **Gemini** (Google AI Studio): il piano A;
  2. **Groq**;
  3. **LM Studio** in locale (raggiunto da Docker via `host.docker.internal`, saltato se non risponde);
  4. **Mock** deterministico basato su regole: sempre disponibile.
- I provider senza chiave configurata vengono saltati.
- **Retry con backoff** sugli errori transitori (timeout, 5xx). Su `429` o quota esaurita il provider va in **cooldown** per un intervallo configurabile (circuit breaker), così le richieste successive non perdono tempo a riprovarlo.
- **Tracciabilità del provider:**
  - ogni messaggio dell'assistente è persistito con `provider` e `model` di chi l'ha generato;
  - la UI mostra un **tag accanto a ogni risposta**: `GEMINI` / `GROQ` / `LMSTUDIO` / `MOCK`;
  - se un turno usa più chiamate (estrazione + risposta), il tag indica chi ha generato il testo mostrato, e il dettaglio di ogni chiamata, compresi i fallback, è nella trace (ADR-0010).
- Lo stesso mock è usato in **test, CI e demo offline**.

## Motivazione

- Con i free tier il fallback è un **requisito** di affidabilità, non un extra.
- Il tag rende visibile ogni degradazione invece di nasconderla: chi vede `MOCK` sa che sta parlando con il sistema di riserva. Per uno strumento AI la trasparenza sul modello che risponde fa parte del prodotto.
- L'ordine segue il piano A e mette in fondo le opzioni che non dipendono da quote esterne.
- Un'API comune riduce l'adapter a poco codice. LiteLLM avrebbe dato più provider, ma qui serve controllo fine su cooldown, tag e trace.

## Conseguenze

- **Positive:** il sistema risponde sempre, il reviewer lo prova senza chiavi, il comportamento in degrado è osservabile.
- **Negative:** i provider hanno capacità diverse (qualità del tool calling, supporto all'output strutturato con JSON Schema). L'adapter deve normalizzarle, e il comportamento può variare tra un turno e l'altro dopo un fallback.
- **Da verificare in implementazione:** il supporto effettivo all'output strutturato di ciascun provider sull'endpoint OpenAI-compatibile, con una strategia di ripiego (JSON in testo + validazione + un retry).
