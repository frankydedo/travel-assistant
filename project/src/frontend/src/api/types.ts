// Tipi del contratto API del backend (FastAPI). Tenere allineati al backend.
// Tutti gli id sono UUID stringa opachi: non se ne deriva alcun significato.

export type Provider = "GEMINI" | "GROQ" | "MOCK" | "SYSTEM";

export type Phase =
  | "COLLECTING_REQUIREMENTS"
  | "PROPOSING"
  | "AWAITING_CONFIRMATION"
  | "BOOKED";

export interface TripRequirements {
  /** "unlimited" and departure "ANY" / categories [] are explicit "any" values (ADR-0021). */
  budget_total: number | "unlimited" | null;
  destination: {
    type: "country" | "suggest" | "anywhere";
    country_code: string | null;
  } | null;
  preferences: { categories: string[]; notes: string | null } | null;
  month: number | null;
  duration: { min_days: number; max_days: number } | null;
  departure_airport: string | null;
  travelers: number | null;
}

export type RequirementField = keyof TripRequirements;

export interface ConfirmBookingUi {
  type: "confirm_booking";
  itinerary_id: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider: Provider | null;
  model: string | null;
  /** true solo per GEMINI/GROQ. MOCK = regole deterministiche, SYSTEM = codice. */
  ai_generated: boolean;
  created_at: string;
  itinerary_ids: string[];
  ui: ConfirmBookingUi | null;
  /** Link alla trace del turno nella UI di Langfuse self-hosted; null se il tracing è spento. */
  trace_url: string | null;
}

export interface Flight {
  id: string;
  flight_number: string;
  carrier: string;
  origin: string;
  destination: string;
  date: string;
  departure_time: string;
  arrival_time: string;
  price_per_person: number;
  subtotal: number;
}

export type ItineraryVariant = "economy" | "balanced" | "premium";
export type ItineraryStatus = "proposed" | "selected" | "booked" | "discarded";

export interface DayPlan {
  day: number;
  date: string;
  /** Giorno di viaggio: gli orari dei voli non lasciano tempo per un'attività (ADR-0023). */
  travel_day?: boolean;
  /** Primo/ultimo giorno: orario di arrivo o del volo di ritorno. */
  travel_note?: string | null;
  activity: {
    id: string;
    name: string;
    category: string;
    description: string;
    duration_hours: number;
    price_per_person: number;
    subtotal: number;
    /** Descrizione del catalogo scritta con AI e rivista. */
    description_ai_generated: boolean;
  } | null;
}

export interface Itinerary {
  id: string;
  conversation_id: string;
  variant: ItineraryVariant;
  status: ItineraryStatus;
  country_code: string;
  country_name: string;
  destination: string;
  start_date: string;
  end_date: string;
  days: number;
  nights: number;
  travelers: number;
  rooms: number;
  total_price: number;
  budget_total: number | null; // null = unlimited budget
  cost_breakdown: { flights: number; hotel: number; activities: number };
  flights: { outbound: Flight; return: Flight };
  hotel: {
    id: string;
    name: string;
    stars: number;
    neighborhood: string;
    nights: number;
    price_per_night_avg: number;
    subtotal: number;
  };
  days_plan: DayPlan[];
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  phase: Phase;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  requirements: TripRequirements;
  missing_fields: RequirementField[];
  messages: Message[];
  itineraries: Itinerary[];
}

export interface Booking {
  id: string;
  status: "confirmed" | "cancelled";
  total_price: number;
  created_at: string;
  cancelled_at: string | null;
  itinerary: Itinerary;
}

export interface Catalog {
  countries: { code: string; name: string; destination: string }[];
  departure_airports: { code: string; city: string; name: string }[];
  categories: { code: string; label: string }[];
}

export interface Me {
  id: string;
  username: string;
  email: string | null;
  name: string | null;
}

// --- Streaming SSE di un turno di chat (POST /conversations/{id}/messages/stream) ---

export type StreamStage = "interpreting" | "planning" | "validating" | "writing";

export interface StreamProgress {
  stage: StreamStage;
  message: string;
}

export interface StreamProviderInfo {
  provider: Provider;
  model: string | null;
  ai_generated: boolean;
}

export interface StreamErrorPayload {
  code: string;
  message: string;
}

// --- Tracing (GET /tracing/summary): metriche lette da Langfuse, solo dell'utente corrente ---

export type TracingPeriod = "24h" | "7d" | "30d";

export interface TracingTotals {
  turns: number;
  llm_calls: number;
  failed_attempts: number;
  /** 0..1 */
  failure_rate: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  avg_turn_latency_ms: number;
  p95_turn_latency_ms: number;
}

export interface TracingModelRow {
  provider: "GROQ" | "GEMINI" | "MOCK" | "—";
  model: string;
  calls: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
}

export interface TracingTaskRow {
  task: string;
  calls: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export interface TracingSeriesPoint {
  /** "YYYY-MM-DD" oppure bucket orario (ISO). */
  bucket: string;
  cost_usd: number;
  calls: number;
}

export interface TracingRecentTurn {
  name: string;
  started_at: string;
  latency_ms: number;
  level: string;
  trace_url: string | null;
}

export interface TracingSummaryAvailable {
  available: true;
  period: TracingPeriod;
  note: string;
  totals: TracingTotals;
  by_model: TracingModelRow[];
  by_task: TracingTaskRow[];
  series: TracingSeriesPoint[];
  recent_turns: TracingRecentTurn[];
}

export interface TracingSummaryUnavailable {
  available: false;
  reason: string;
}

export type TracingSummary = TracingSummaryAvailable | TracingSummaryUnavailable;
