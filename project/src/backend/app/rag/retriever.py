"""Activity retrieval for RAG (ADR-0004).

One document per activity. The metadata filter on country and month is mandatory: similarity only
ranks, it never decides what is admissible. The relational DB stays the source of truth; Chroma holds a
projection keyed by the same activity id.
"""

import logging
import re
from functools import lru_cache
from typing import Protocol

from app.domain.requirements import CATEGORIES, Preferences

log = logging.getLogger(__name__)

COLLECTION = "activities"
SEMANTIC_WEIGHT = 0.6
CATEGORY_WEIGHT = 0.4


class ActivityDoc(Protocol):
    id: str
    name: str
    category: str
    targets: list[str]
    description: str
    country_code: str
    months: list[int]


def document_text(a: ActivityDoc) -> str:
    targets = ", ".join(a.targets)
    return f"{a.name}. Categoria: {CATEGORIES.get(a.category, a.category)}. Ideale per: {targets}. {a.description}"


def query_text(preferences: Preferences) -> str:
    labels = ", ".join(CATEGORIES[c] for c in preferences.categories)
    return f"Attività di tipo {labels}. {preferences.notes or ''}".strip()


class SemanticIndex(Protocol):
    def similarities(self, query: str, country_codes: list[str], month: int) -> dict[str, float]: ...


def score_activities(
    index: SemanticIndex,
    preferences: Preferences,
    activities: list[ActivityDoc],
    country_codes: list[str],
    month: int,
) -> dict[str, float]:
    """Preference score in [0, 1] for every candidate activity: semantic similarity (min-max normalised
    within the candidates) blended with an exact category match."""
    candidates = [a for a in activities if a.country_code in country_codes]
    raw = index.similarities(query_text(preferences), country_codes, month)
    values = [raw[a.id] for a in candidates if a.id in raw]
    lo, hi = (min(values), max(values)) if values else (0.0, 0.0)
    scores: dict[str, float] = {}
    for a in candidates:
        semantic = (raw[a.id] - lo) / (hi - lo) if a.id in raw and hi > lo else (1.0 if a.id in raw else 0.0)
        category = 1.0 if a.category in preferences.categories else 0.0
        scores[a.id] = round(SEMANTIC_WEIGHT * semantic + CATEGORY_WEIGHT * category, 4)
    return scores


# --- Chroma + local multilingual embeddings ----------------------------------------------


@lru_cache(maxsize=2)
def _embedder(model_name: str, cache_dir: str | None):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cache_dir=cache_dir)


class ChromaIndex:
    def __init__(self, path: str, model_name: str, cache_dir: str | None = None):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self.model_name = model_name
        self.cache_dir = cache_dir

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in _embedder(self.model_name, self.cache_dir).embed(texts)]

    def reindex(self, activities: list[ActivityDoc]) -> int:
        """Idempotent: upsert by activity id, and drop documents no longer in the catalog."""
        collection = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        ids = [a.id for a in activities]
        existing = set(collection.get(include=[])["ids"])
        stale = list(existing - set(ids))
        if stale:
            collection.delete(ids=stale)
        if activities:
            metadatas = []
            for a in activities:
                meta: dict[str, str | bool] = {"country": a.country_code, "category": a.category}
                meta.update({f"m{m}": m in a.months for m in range(1, 13)})
                metadatas.append(meta)
            texts = [document_text(a) for a in activities]
            collection.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=self._embed(texts))
        return len(activities)

    def similarities(self, query: str, country_codes: list[str], month: int) -> dict[str, float]:
        collection = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        count = collection.count()
        if count == 0:
            return {}
        where = {"$and": [{"country": {"$in": country_codes}}, {f"m{month}": True}]}
        result = collection.query(
            query_embeddings=self._embed([query]), n_results=count, where=where, include=["distances"]
        )
        return {i: 1.0 - d for i, d in zip(result["ids"][0], result["distances"][0], strict=True)}


# --- Keyword fallback (tests, or when the embedding model is unavailable) -------------------

_WORD = re.compile(r"[a-zàèéìòù]{4,}")


class KeywordIndex:
    """Token-overlap similarity. Deterministic and dependency-free; same metadata filter as Chroma."""

    def __init__(self, activities: list[ActivityDoc]):
        self.activities = activities

    def similarities(self, query: str, country_codes: list[str], month: int) -> dict[str, float]:
        query_tokens = {w[:5] for w in _WORD.findall(query.lower())}
        out: dict[str, float] = {}
        for a in self.activities:
            if a.country_code not in country_codes or month not in a.months:
                continue
            tokens = {w[:5] for w in _WORD.findall(document_text(a).lower())}
            out[a.id] = len(query_tokens & tokens) / (len(query_tokens) or 1)
        return out
