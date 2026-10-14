# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Phase 1 (end-to-end slice) and most of Phase 2 (real providers Groq/Gemini via `app/llm/openai_compat.py`, adaptive structured output, SSE streaming) are implemented. Real API keys live only in `project/.env` (gitignored): never print, log or commit them. `tracker.md` is the source of truth for what is done and to do: keep it updated, and record implementation-level decisions in its last section.

Commands:

- Layout: docs and project context at the root; everything runnable under `project/` (compose, `.env.example`, `infra/`, `src/backend`, `src/frontend`).
- Backend (`project/src/backend/`, Python 3.12 via uv; on this Mac use the arm64 interpreter already in its `.venv`): `uv run pytest` (PostgreSQL via testcontainers, so Docker must be running; mock provider; never switch tests to SQLite, ADR-0014), `uv run ruff check .`
- Frontend (`project/src/frontend/`): `npm run build` (includes `tsc --noEmit`), `npm run dev`
- Everything: `cd project && docker compose up --build` (app on :3000, API on :8000, Keycloak on :8080)
- Code comments and identifiers are in English; user-facing strings and docs are in Italian.
- **Every id is a UUID** (`Uuid(as_uuid=False)` columns, `uuid_pk()` in `app/models.py`): catalog ids are deterministic via `catalog_id(kind, slug)`, runtime ids random. API path/body ids and the Idempotency-Key are typed `UUID` (422 if malformed). ISO country and IATA airport codes stay natural keys.

- `CHALLENGE.md`: the original challenge brief (Italian). It is **gitignored on purpose** and must not be committed to the delivered repo. Read it for requirements, but don't reference it from committed files.
- `docs/adr/`: **the source of truth for architectural decisions** (ADR-0001 to 0019, Italian). Read the relevant ADR before implementing a component. An accepted ADR is never edited; a changed decision gets a new ADR that supersedes it. ADRs with status `Proposta` are not settled (none at the moment), so check with the user before relying on them. "Da verificare" marks claims still to be checked during implementation.
- `docs/engineering-challenges.md`: the overview of the challenges and decisions, linking to the ADRs.
- `docs/workflow-prenotazione.md`: Mermaid diagrams of the booking flow (trust zones, phase state machine, full sequence). The LLM component is called **"Interprete LLM"**, not "agent": it interprets and explains, and only *proposes* tool calls that the orchestrator validates. Keep the diagrams in sync when the flow changes.
- `docs/ai-usage.md`: the user's living log of how AI is used in development (part of the evaluation). Record in its *Registro* table any case where the user corrected or changed an AI proposal, or where the AI changed the user's. The document must not contain dates or a timeline.

Project docs are written in Italian. Keep new docs in Italian unless the user asks otherwise.

## What is being built

A conversational travel assistant. It collects budget, country, activity preferences and travel month through chat. It then builds a full itinerary (round-trip flight, a hotel for every night, an activity for every day) within the budget and availability limits, and lets the user book it through chat. Required pieces:

- PostgreSQL (ADR-0014; one instance with separate databases for app, Keycloak and Langfuse) with users, hotels (per-date availability and price), activities, flights and bookings.
- Vector DB for RAG over activity descriptions and target audiences.
- FastAPI REST backend, React (Vite) frontend.
- Frontend with registration/login, chat, itinerary display, booking via chat, a bookings dashboard and a Tracing page.

The reviewer cares about architectural choices, priorities and trade-offs more than completeness or UI polish. How generative AI was used in development is explicitly part of the evaluation. Time is limited, so scope is prioritized (ADR-0015).

## Guiding architectural principle

**"The LLM understands and explains; the code decides and guarantees."** Key decisions (see the ADRs for details):

- **Hybrid control flow** (0001): an explicit backend state machine drives the phases (collecting requirements → proposing → awaiting confirmation → booked). LLM tool calling happens only *inside* a phase, with only that phase's tools.
- **Slot filling** (0002): `TripRequirements` is a persisted structured object, updated every turn from Pydantic-validated structured output. **Every field is required and starts as `null`, with no silent defaults.** Flexible values: destination can be a country, `suggest` (the LLM picks, but only among countries the code found feasible) or `anywhere` (no country filter); duration is a `{min, max}` range; dates are month-only and the planner picks the start date. Cost assumptions: N days = N-1 nights, flights and activities are priced per person, rooms hold 2 people.
- **Deterministic planner** (0003): `Planner` interface with `GreedyPlanner` and 3 variants (economy, balanced, premium). A separate deterministic validator checks every itinerary. If nothing is feasible, it returns the blocking constraints and possible relaxations. No ILP for now.
- **RAG** (0004): Chroma embedded, one document per activity, local multilingual `sentence-transformers` embeddings, mandatory metadata filter on country and month, relational DB as source of truth.
- **LLM providers** (0005): an own adapter over the OpenAI-compatible API. Fallback chain **Groq → Gemini → Mock** (order from ADR-0018, LM Studio removed by ADR-0019), with backoff and a cooldown on 429/quota errors. **Every assistant message is persisted with its provider and model and shows a tag in the chat** (`GROQ`/`GEMINI`/`MOCK`/`SYSTEM`). The deterministic rule-based mock is also used by tests, CI and the evals baseline.
- **Booking safety** (0006): only through an explicit UI button. The endpoint receives only `itinerary_id` and an idempotency key. It runs a single transaction with conditional atomic inventory decrement, re-checks availability and stores a price snapshot.
- **Proposal tools** (0001, `app/services/proposal_tools.py`): native tool calling in the proposal phase, bounded to 3 steps. The LLM never sees ids (it refers to variant + day). Tool args are only primitives/enums. Modifications create a new validated itinerary. Select/update/out-of-scope are terminal and hand control back to the orchestrator. The mock emulates tool choice with rules (`choose_tool`). Provider-specific tool-call fields (Gemini `thought_signature`) are sent back only to the same provider.
- **Domain guardrail** (0016): only travel-related requests are answered. The scope verdict comes inside the existing structured calls (`Extraction.in_scope`, `ProposalAction.out_of_scope`), so there are no extra LLM calls. The refusal is a fixed text written by code (`SYSTEM` tag), and phase and requirements stay unchanged. Greetings and short acknowledgements are in scope.
- **AI guardrails** (0007): `user_id` always comes from the JWT, tool calls are schema-validated with IDs checked against the DB, plus a per-user rate limit and no file uploads.
- **Evals** (0008): golden set, deterministic metrics, and LLM-as-judge only for subjective aspects. Evals run per provider with the mock as baseline. Only the deterministic evals on the mock run in CI.
- **History + compaction** (0009): all messages are persisted. Above a token threshold (default about 8k), older messages are summarized by the LLM into the new starting context, plus the last few turns. Structured state is never summarized, and the user-visible history stays complete.
- **Observability** (0010): **self-hosted Langfuse in docker-compose**, with keys pre-created through headless init. Each turn is a trace and each LLM call a generation. The estimated list-price cost is computed by the backend. The UI Tracing page reads Langfuse metrics through the backend. Tracing is best-effort: the app works if Langfuse is down.
- **Markdown replies**: prompts ask for Markdown (`MARKDOWN_RULE` in `interpreter.py`). The frontend `Markdown` component renders a safe subset only: no raw HTML, links, images, headings or tables, because LLM output is untrusted. User messages stay plain text.
- **Logging** (0017): structured JSON on stdout with stable event names (`booking.confirmed`, `llm.call`, …) through `logging` + `extra={...}`, never message text, prompts or tokens. Context (request_id, user_id, conversation_id) comes from contextvars in `app/logging_setup.py`. LLM content belongs in Langfuse, business records in the DB.
- **Streaming** (0011): SSE with typed events (`progress`, `token`, `itinerary`, `done`, `error`). The client uses `fetch` + `ReadableStream`, not `EventSource`, because it needs the `Authorization` header. No WebSocket.
- **Auth** (0012): Keycloak with a pre-imported realm (test users, self-registration) and the frontend using OIDC Code + PKCE. The backend only validates JWTs and provisions users just-in-time from `sub`. Keycloak only: no social login.
- **Data** (0013): 5 countries (Italia, Spagna, Grecia, Giappone, Islanda) and 3 departure airports (FCO, MXP, NAP). A deterministic seeded script generates data with a calendar relative to the seed month and deliberate edge cases. Activity descriptions are written once with AI and committed as JSON fixtures.

## Scope and build order (ADR-0015)

Build an end-to-end slice with the mock first, then add layers in order of value. Each phase must leave the system working:

1. Compose + DB, seed + RAG index, Keycloak, state machine + slot filling (mock), planner + validator, booking, chat + itinerary cards + bookings dashboard, messages with provider tag.
2. Real providers + fallback chain + cooldown, SSE.
3. Langfuse self-hosted + Tracing page + estimated costs.
4. Golden set, metrics, judge, CI.
5. Compaction, conversation resume.
6. Editing bookings.

**Excluded on purpose (documented with reasons in ADR-0015)**: message broker, image upload/multimodal, ILP solver, social login (Google), WebSocket, free-form LLM agent, payments, cloud deploy, Claude subscription as a runtime provider. Don't add these without discussing it with the user first.

## Reviewer experience constraints

- `docker compose up` must work out of the box: automatic seeding, `.env.example`, pre-imported Keycloak realm, Langfuse with pre-created keys, and the mock as safety net. Document the RAM needs of the full compose in the README.
- Document the brief's gaps and the assumptions made in the README.
- Testing: unit tests for the planner, validator and state machine; API integration tests with the mock provider; evals separate from tests.
