// Parser minimo di text/event-stream (sottoinsieme della specifica WHATWG che serve qui).
// Funzione pura e senza stato: chi legge lo stream conserva `rest` e lo ripassa insieme al chunk successivo.
// Gestisce chunk spezzati a metà riga, più eventi nello stesso chunk e terminatori \n, \r\n e \r.

export interface SseEvent {
  /** Nome dell'evento (`event:`); "message" se assente. */
  event: string;
  /** Righe `data:` unite con "\n". */
  data: string;
}

export interface SseParseResult {
  events: SseEvent[];
  /** Testo non ancora completo (evento senza riga vuota finale): va anteposto al chunk successivo. */
  rest: string;
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // riga vuota o commento (es. keep-alive)
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    // id e retry non servono: niente riconnessione automatica.
  }
  // Come da specifica, un blocco senza `data:` non genera eventi.
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

/**
 * Estrae gli eventi completi da `buffer` (= rest precedente + nuovo chunk decodificato).
 * Con `final: true` (fine dello stream) anche l'ultimo evento senza riga vuota finale viene emesso.
 */
export function parseSseChunk(buffer: string, final = false): SseParseResult {
  let text = buffer;
  let tail = "";
  // Un \r finale potrebbe essere la prima metà di un \r\n spezzato tra due chunk: lo si tiene da parte.
  if (!final && text.endsWith("\r")) {
    tail = "\r";
    text = text.slice(0, -1);
  }
  text = text.replace(/\r\n?/g, "\n");
  if (final) text += "\n\n";

  const end = text.lastIndexOf("\n\n");
  if (end === -1) return { events: [], rest: text + tail };

  const events = text
    .slice(0, end)
    .split("\n\n")
    .map(parseBlock)
    .filter((e): e is SseEvent => e !== null);
  return { events, rest: final ? "" : text.slice(end + 2) + tail };
}
