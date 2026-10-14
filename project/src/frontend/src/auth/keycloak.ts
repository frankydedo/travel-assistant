import Keycloak from "keycloak-js";

// Configurazione da env Vite, con default per lo sviluppo locale.
export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "travel",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "travel-frontend",
});

export function initKeycloak(): Promise<boolean> {
  return keycloak.init({
    onLoad: "login-required",
    pkceMethod: "S256",
    checkLoginIframe: false,
  });
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

export function logout(): void {
  void keycloak.logout({ redirectUri: window.location.origin });
}
