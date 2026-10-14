"""Dependency wiring: one gateway and one semantic index per process, one service per request."""

import logging
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.llm.interpreter import Interpreter
from app.llm.registry import build_gateway
from app.models import Activity
from app.rag.retriever import ChromaIndex, KeywordIndex, SemanticIndex
from app.ratelimit import RateLimiter
from app.services.conversation import ConversationService

log = logging.getLogger(__name__)


@lru_cache
def get_interpreter() -> Interpreter:
    return Interpreter(build_gateway(get_settings()))


@lru_cache
def _chroma() -> ChromaIndex | None:
    settings = get_settings()
    try:
        return ChromaIndex(settings.chroma_path, settings.embedding_model, settings.embedding_cache_dir)
    except Exception:  # pragma: no cover - depends on the environment
        log.exception("Chroma unavailable, falling back to keyword retrieval")
        return None


def index_factory(activities: list[Activity]) -> SemanticIndex:
    if get_settings().retriever == "chroma":
        chroma = _chroma()
        if chroma is not None:
            return chroma
    return KeywordIndex(activities)


@lru_cache
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(settings.rate_limit_messages, settings.rate_limit_window_seconds)


def get_conversation_service(
    session: Session = Depends(get_session),
    interpreter: Interpreter = Depends(get_interpreter),
    settings: Settings = Depends(get_settings),
) -> ConversationService:
    return ConversationService(session, interpreter, index_factory, settings)
