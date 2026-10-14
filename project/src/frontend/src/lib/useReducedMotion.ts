import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(listener: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", listener);
  return () => mql.removeEventListener("change", listener);
}

const getSnapshot = () => typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;

/** true se l'utente ha chiesto di ridurre le animazioni (serve per le animazioni SMIL, che il CSS non controlla). */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot);
}
