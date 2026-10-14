# ADR-0018 — Ordine della catena: Groq prima di Gemini

- **Stato:** Accettata (sostituisce l'ordine della catena di [ADR-0005](0005-provider-llm-catena-fallback.md)) · LM Studio rimosso con [ADR-0019](0019-rimozione-lm-studio.md)

## Contesto

ADR-0005 aveva fissato l'ordine Gemini → Groq → LM Studio → Mock, scegliendo Gemini come piano A. Con le chiavi reali abbiamo misurato i provider sui task veri del sistema: estrazione di una richiesta complessa, verdetto di scope, scrittura della risposta e tool calling.

## Dati raccolti

| Provider e modello | Estrazione | Risposta | Note |
|---|---|---|---|
| Gemini `gemini-flash-lite-latest` | 1-5 s | 3-8 s al primo token | Turno completo di 9-14 s in Docker |
| Gemini `gemini-3.8-flash` | ~6 s | — | Il più accurato, ma spesso in 503 "high demand" |
| Groq `openai/gpt-oss-120b` | ~0,9 s | ~0,4 s | Estrazione corretta su tutti i casi provati |

Sui casi provati la qualità di estrazione e tool calling è equivalente tra i due provider di default, mentre la latenza differisce di circa cinque volte.

## Decisione

- **Nuovo ordine:** Groq → Gemini → LM Studio → Mock.
- Il meccanismo di ADR-0005 resta invariato: fallback, cooldown, tag del provider, mock come ultimo anello.
- L'ordine resta configurabile da `LLM_CHAIN`.

## Motivazione

In una chat la latenza è parte della qualità percepita. A parità di correttezza sui nostri casi conviene il provider più rapido, e Gemini diventa la riserva in caso di quota esaurita o errori. La scelta è basata su misure e non su preferenze, ed è reversibile con una variabile d'ambiente.

## Conseguenze

- **Positive:** turni di chat molto più rapidi.
- **Negative:** i limiti di token al minuto del free tier di Groq si raggiungono prima. In quel caso il cooldown passa a Gemini, e il tag in chat lo rende visibile.
- **Da misurare:** il confronto tra provider va ripetuto sul golden set (ADR-0008); i casi provati finora sono pochi.
