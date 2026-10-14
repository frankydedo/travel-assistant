# ADR-0012 — Autenticazione con Keycloak

- **Stato:** Accettata
- **Riferimenti:** [engineering-challenges §C1](../engineering-challenges.md#c1-autenticazione--adr-0012)

## Contesto

La traccia richiede registrazione e autenticazione degli utenti. Il sistema deve funzionare con `docker compose up`, senza che il reviewer configuri servizi esterni.

## Opzioni considerate

| Opzione | Pro | Contro |
|---|---|---|
| JWT fatto in casa | Minimo | Reinventa la sicurezza (hash, reset password, rotazione chiavi) |
| Google SSO diretto | Familiare per l'utente | Il reviewer deve creare un OAuth client su Google Cloud |
| **Keycloak** | Standard OIDC, registrazione e login pronti, ruoli | Container pesante, configurazione del realm |
| Keycloak + login Google federato | Due metodi di login | Segreti Google da gestire e lavoro in più, senza valore per la valutazione |

## Decisione

- **Keycloak** in docker-compose con un **realm pre-importato**:
  - client pubblico per il frontend;
  - utenti di test documentati nel README;
  - **self-registration attiva**, che copre il requisito di registrazione della traccia.
- **Frontend:** OIDC Authorization Code + PKCE.
- **Backend:** valida solo i JWT (firma via JWKS, issuer, audience, scadenza).
- **Utenti nel DB applicativo:** il record `users` viene creato al primo accesso dal claim `sub` (provisioning just-in-time). Le prenotazioni referenziano questo utente.
- **Nessun login social.**

## Motivazione

- È uno standard di settore, e non c'è codice di sicurezza scritto a mano.
- Il realm pre-importato rende l'avvio immediato per il reviewer.
- Il login Google federato è stato scartato perché richiede segreti che il reviewer non ha e aggiunge lavoro senza rafforzare il nucleo del progetto.

## Conseguenze

- **Positive:** login, registrazione e logout completi. Il backend dipende solo da OIDC, quindi qualsiasi identity provider futuro (es. Google, SSO aziendale) si aggiunge in Keycloak senza toccare il backend.
- **Negative:** un container in più e qualche secondo di avvio. Il realm va mantenuto come file versionato.
