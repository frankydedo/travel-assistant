import Keycloak from "keycloak-js";

// Configurazione da env Vite, con default per lo sviluppo locale.
export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "travel",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "travel-frontend",
});

/**
 * check-sso: verifica in un iframe nascosto se esiste già una sessione Keycloak, senza redirect.
 * Se non c'è sessione l'app mostra la landing e il login parte solo dal pulsante.
 * Con i cookie di terze parti bloccati keycloak-js ripiega da solo su un redirect con prompt=none
 * (silentCheckSsoFallback, attivo di default).
 */
export function initKeycloak(): Promise<boolean> {
  return keycloak.init({
    onLoad: "check-sso",
    silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
    pkceMethod: "S256",
    checkLoginIframe: false,
  });
}

/** Avvia il login (redirect a Keycloak); al ritorno si riapre la pagina corrente. */
export function login(): Promise<void> {
  return keycloak.login();
}

/** Apre il modulo di registrazione self-service del realm. */
export function register(): Promise<void> {
  return keycloak.register();
}

/** Restituisce un access token valido, rinnovandolo se scade entro 30 secondi. */
export async function getToken(): Promise<string> {
  try {
    await keycloak.updateToken(30);
  } catch {
    // Refresh token scaduto o sessione chiusa: si torna al login.
    await keycloak.login();
    throw new Error("Sessione scaduta");
  }
  if (!keycloak.token) throw new Error("Token non disponibile");
  return keycloak.token;
}

export function tokenDisplayName(): string {
  const t = keycloak.tokenParsed as Record<string, unknown> | undefined;
  const name = t?.["name"] ?? t?.["preferred_username"];
  return typeof name === "string" ? name : "";
}

/** Chiude la sessione Keycloak e torna alla landing. */
export function logout(): void {
  void keycloak.logout({ redirectUri: window.location.origin });
}
