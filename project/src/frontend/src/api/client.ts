// Unico modulo che parla HTTP con il backend. Tutte le chiamate passano da qui.
import { getToken } from "../auth/keycloak";
import type {
  Booking,
  Catalog,
  ConversationDetail,
  ConversationSummary,
  Me,
} from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Errore di rete (richiesta non arrivata o risposta persa): l'esito lato server è ignoto. */
export class NetworkError extends Error {
  constructor(message = "Errore di rete: impossibile contattare il server") {
    super(message);
    this.name = "NetworkError";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let message = `Errore ${res.status}`;
  let code: string | null = null;
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      // Errori di validazione FastAPI (422).
      message = detail
        .map((d) => (d as { msg?: unknown })?.msg)
        .filter((m): m is string => typeof m === "string")
        .join("; ") || message;
    } else if (detail && typeof detail === "object") {
      const d = detail as { code?: unknown; message?: unknown };
      if (typeof d.message === "string") message = d.message;
      if (typeof d.code === "string") code = d.code;
    }
  } catch {
    // Corpo non JSON: si tiene il messaggio generico.
  }
  if (res.status === 429) {
    message = "Troppi messaggi, riprova tra poco";
  }
  return new ApiError(res.status, message, code);
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
    ...extraHeaders,
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new NetworkError();
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const getMe = () => request<Me>("GET", "/me");

export const getCatalog = () => request<Catalog>("GET", "/catalog");

export const listConversations = () =>
  request<ConversationSummary[]>("GET", "/conversations");

export const createConversation = () =>
  request<ConversationDetail>("POST", "/conversations");

export const getConversation = (id: string) =>
  request<ConversationDetail>("GET", `/conversations/${encodeURIComponent(id)}`);

/**
 * Invia un messaggio e restituisce lo stato completo aggiornato della conversazione.
 * Isolata di proposito: una fase successiva la sostituirà con lo streaming SSE.
 */
export function sendMessage(
  conversationId: string,
  content: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    "POST",
    `/conversations/${encodeURIComponent(conversationId)}/messages`,
    { content },
  );
}

export const selectItinerary = (itineraryId: string) =>
  request<ConversationDetail>(
    "POST",
    `/itineraries/${encodeURIComponent(itineraryId)}/select`,
  );

export const createBooking = (itineraryId: string, idempotencyKey: string) =>
  request<Booking>(
    "POST",
    "/bookings",
    { itinerary_id: itineraryId },
    { "Idempotency-Key": idempotencyKey },
  );

export const listBookings = () => request<Booking[]>("GET", "/bookings");

export const cancelBooking = (bookingId: string) =>
  request<Booking>("POST", `/bookings/${encodeURIComponent(bookingId)}/cancel`);

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Errore imprevisto";
}
