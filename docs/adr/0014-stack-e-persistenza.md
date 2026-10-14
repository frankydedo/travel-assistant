# ADR-0014 — Stack applicativo e persistenza

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §B5](../engineering-challenges.md#b5-stack-e-persistenza--adr-0014)

## Contesto

La traccia suggerisce Flask o FastAPI per il backend e lascia libero il frontend. Per il DB principale ammette relazionale o NoSQL. Il sistema ha già bisogno di Postgres per Langfuse self-hosted (ADR-0010), e le prenotazioni richiedono transazioni e controllo della concorrenza (ADR-0006).

## Opzioni considerate

- **Backend:** FastAPI · Flask.
- **Frontend:** React · HTML/JS semplice.
- **DB principale:** SQLite · PostgreSQL · NoSQL (es. MongoDB).

## Decisione

**Stack:**

- **FastAPI**: async nativo (utile per SSE e per le chiamate LLM), validazione Pydantic integrata, coerente con lo slot filling (ADR-0002), OpenAPI generata automaticamente;
- **React** (Vite) per il frontend;
- **SQLAlchemy 2** + **Alembic** per ORM e migrazioni.

**Persistenza:**

- **PostgreSQL**, in una sola istanza con database separati per app, Keycloak e Langfuse.
- Era stato inizialmente indicato SQLite per semplicità. Con l'arrivo di Langfuse self-hosted, Postgres è già nello stack, quindi passare a Postgres **non aggiunge infrastruttura**.
- Postgres offre concorrenza reale sulle scritture (SQLite serializza tutte le scritture), lock di riga se servissero ed è più vicino a un ambiente di produzione.
- I dati sono fortemente relazionali (disponibilità per data, prenotazioni che referenziano più risorse), quindi il NoSQL non porta vantaggi.

## Motivazione

FastAPI e Pydantic sono lo standard per i backend Python con componenti LLM. Il passaggio a Postgres sfrutta un componente già presente invece di affiancarne un secondo.

## Conseguenze

- **Positive:** un solo motore DB nello stack, test di integrazione realistici.
- **Negative:** i test richiedono un Postgres (container in CI) invece di un file SQLite.
