// Unico modulo che parla HTTP con il backend. Tutte le chiamate passano da qui.
import { getToken } from "../auth/keycloak";
import { parseSseChunk, type SseEvent } from "./sse";
import type {
  Booking,
  Catalog,
  ConversationDetail,
  ConversationSummary,
  Me,
  StreamErrorPayload,
  StreamProgress,
  StreamProviderInfo,
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
  method: "GET" | "POST" | "PATCH" | "DELETE",
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

/** Rinomina una conversazione (titolo 1-80 caratteri, già ripulito dagli spazi). */
export const renameConversation = (id: string, title: string) =>
  request<ConversationSummary>("PATCH", `/conversations/${encodeURIComponent(id)}`, { title });

/** Elimina una conversazione (204 senza corpo). Le prenotazioni confermate restano. */
export const deleteConversation = (id: string) =>
  request<void>("DELETE", `/conversations/${encodeURIComponent(id)}`);

/**
 * Invia un messaggio e restituisce lo stato completo aggiornato della conversazione (senza streaming).
 * Resta come ripiego di sendMessageStream.
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

/** Evento `error` inviato dal server a stream già avviato. */
export class StreamError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "StreamError";
    this.code = code;
  }
}

/** Stream interrotto dopo l'inizio (rete o chiusura senza `done`): l'esito del turno va riletto dal server. */
export class StreamInterruptedError extends Error {
  constructor(message = "La connessione si è interrotta durante la risposta") {
    super(message);
    this.name = "StreamInterruptedError";
  }
}

export interface StreamHandlers {
  /** Avanzamento del turno (interpretazione, planner, validazione, scrittura). */
  onProgress?: (progress: StreamProgress) => void;
  /** Inizio di una risposta in streaming: chi la sta generando. */
  onProvider?: (info: StreamProviderInfo) => void;
  /** Frammento di testo da accodare alla risposta. */
  onToken?: (text: string) => void;
  /** Il provider è fallito a metà: il testo ricevuto finora va scartato (ne arriverà un altro). */
  onReset?: () => void;
  /** Si sta ripiegando sull'endpoint senza streaming. */
  onFallback?: () => void;
}

function parseJson(data: string): unknown {
  try {
    return JSON.parse(data) as unknown;
  } catch {
    return null;
  }
}

/**
 * Invia un messaggio e riceve la risposta via SSE.
 * Si usa fetch + ReadableStream invece di EventSource, che non permette di inviare l'header Authorization.
 * Risolve con lo stato completo della conversazione (evento `done`), come sendMessage.
 *
 * Errori:
 * - prima dello stream (404/422/429…): ApiError, come l'endpoint senza streaming;
 * - evento `error`: StreamError;
 * - stream interrotto dopo l'inizio: StreamInterruptedError.
 * Ripiego (una sola volta) su sendMessage se l'endpoint risponde 404/405 o se la richiesta non riceve
 * alcuna risposta. Una volta ricevuta la risposta 200 non si ripiega: il server sta già elaborando il turno
 * e un secondo invio duplicherebbe il messaggio.
 */
export async function sendMessageStream(
  conversationId: string,
  content: string,
  handlers: StreamHandlers = {},
): Promise<ConversationDetail> {
  const fallback = () => {
    handlers.onFallback?.();
    return sendMessage(conversationId, content);
  };

  const token = await getToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    });
  } catch {
    return fallback();
  }

  // 404/405: endpoint di streaming assente. Se invece il 404 riguarda la conversazione,
  // l'endpoint classico restituisce lo stesso errore e lo si mostra come prima.
  if (res.status === 404 || res.status === 405) return fallback();
  if (!res.ok) throw await parseError(res);

  // Tolleranza: un backend che risponde con il JSON completo invece dello stream.
  if (!(res.headers.get("content-type") ?? "").includes("text/event-stream")) {
    return (await res.json()) as ConversationDetail;
  }
  if (!res.body) throw new StreamInterruptedError();

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let rest = "";

  /** Gestisce un evento; restituisce la conversazione finale se l'evento è `done`. */
  const handle = (ev: SseEvent): ConversationDetail | null => {
    const data = parseJson(ev.data);
    switch (ev.event) {
      case "progress":
        if (data && typeof data === "object") handlers.onProgress?.(data as StreamProgress);
        return null;
      case "provider":
        if (data && typeof data === "object") handlers.onProvider?.(data as StreamProviderInfo);
        return null;
      case "token": {
        const text = (data as { text?: unknown } | null)?.text;
        if (typeof text === "string") handlers.onToken?.(text);
        return null;
      }
      case "reset":
        handlers.onReset?.();
        return null;
      case "done":
        if (!data || typeof data !== "object") throw new StreamInterruptedError();
        return data as ConversationDetail;
      case "error": {
        const e = (data ?? {}) as Partial<StreamErrorPayload>;
        throw new StreamError(
          typeof e.code === "string" ? e.code : "stream_error",
          typeof e.message === "string" ? e.message : "Si è verificato un errore durante la risposta",
        );
      }
      default:
        return null; // eventi sconosciuti ignorati (compatibilità in avanti)
    }
  };

  try {
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch {
        throw new StreamInterruptedError();
      }
      const text = chunk.done ? decoder.decode() : decoder.decode(chunk.value, { stream: true });
      const parsed = parseSseChunk(rest + text, chunk.done);
      rest = parsed.rest;
      for (const ev of parsed.events) {
        const detail = handle(ev);
        if (detail) return detail;
      }
      if (chunk.done) throw new StreamInterruptedError();
    }
  } finally {
    reader.cancel().catch(() => {
      // Stream già chiuso.
    });
  }
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
