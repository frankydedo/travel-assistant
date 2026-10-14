// Tema chiaro/scuro con dark mode a classe (`.dark` su <html>). Due soli stati, scelti dall'utente.
// La stessa logica, in forma minima, è duplicata nello script inline di index.html
// per applicare il tema prima del primo render ed evitare il lampo del tema sbagliato.
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "theme";

function isTheme(v: unknown): v is Theme {
  return v === "light" || v === "dark";
}

/** Al primo accesso il valore iniziale viene dal sistema operativo, poi resta la scelta salvata. */
function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (isTheme(stored)) return stored;
  } catch {
    // Storage non disponibile: si usa il valore iniziale senza salvarlo.
  }
  const prefersDark = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const theme: Theme = prefersDark ? "dark" : "light";
  writeStored(theme);
  return theme;
}

function writeStored(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage non disponibile (navigazione privata, cookie bloccati): la scelta vale solo per la sessione.
  }
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

let current: Theme = initialTheme();
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

export function setTheme(theme: Theme): void {
  current = theme;
  writeStored(theme);
  apply(theme);
  emit();
}

// Allinea le altre schede aperte quando la scelta cambia.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key !== THEME_STORAGE_KEY || !isTheme(e.newValue)) return;
    current = e.newValue;
    apply(current);
    emit();
  });
}

apply(current);

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, () => current);
  return [theme, setTheme];
}
