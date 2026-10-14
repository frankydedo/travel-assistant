"""OIDC JWT validation against Keycloak (ADR-0012) and just-in-time user provisioning.

The backend only validates tokens: it does not know which identity provider authenticated the user.
The user id used everywhere else comes from here, never from the request body or the LLM (ADR-0007).
"""

import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.logging_setup import user_id_var
from app.models import User

bearer = HTTPBearer(auto_error=False)
log = logging.getLogger(__name__)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        log.warning("auth.invalid_token", extra={"reason": type(exc).__name__})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido") from exc


def provision_user(session: Session, claims: dict) -> User:
    user = session.scalar(select(User).where(User.sub == claims["sub"]))
    if user is None:
        user = User(
            sub=claims["sub"],
            username=claims.get("preferred_username") or claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
        )
        session.add(user)
        session.commit()
        log.info("auth.user_provisioned", extra={"user_id": user.id})
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    """Async on purpose: the user id is set in the request's own context, so every later log line of the
    request carries it (sync dependencies run in separate threads with a copied context)."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticazione richiesta")
    claims = await run_in_threadpool(decode_token, credentials.credentials)  # JWKS fetch may block
    user = await run_in_threadpool(provision_user, session, claims)
    user_id_var.set(user.id)
    return user
