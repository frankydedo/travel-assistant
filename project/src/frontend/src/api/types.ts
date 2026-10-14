// Tipi del contratto API del backend (FastAPI). Tenere allineati al backend.
// Tutti gli id sono UUID stringa opachi: non se ne deriva alcun significato.

export type Provider = "GEMINI" | "GROQ" | "LMSTUDIO" | "MOCK" | "SYSTEM";

export type Phase =
  | "COLLECTING_REQUIREMENTS"
  | "PROPOSING"
  | "AWAITING_CONFIRMATION"
  | "BOOKED";

export interface TripRequirements {
  budget_total: number | null;
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
  /** true solo per GEMINI/GROQ/LMSTUDIO. MOCK = regole deterministiche, SYSTEM = codice. */
  ai_generated: boolean;
  created_at: string;
  itinerary_ids: string[];
  ui: ConfirmBookingUi | null;
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
  };
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
  budget_total: number;
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
