"""``python -m app.seed [--force]``: seed the catalog (once) and (re)index activities in Chroma.

Idempotent: the catalog is generated only if missing (or with --force); reindexing is an upsert.
"""

import argparse
import logging

from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.logging_setup import configure_logging
from app.models import Activity, CatalogMeta
from app.rag.retriever import ChromaIndex
from app.seed.demo import seed_demo
from app.seed.generate import generate

log = logging.getLogger("seed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="regenerate the catalog even if present")
    parser.add_argument("--no-demo", action="store_true", help="skip the pre-loaded demo conversations")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    with session_factory()() as session:
        if args.force or session.scalar(select(CatalogMeta)) is None:
            stats = generate(session)
            log.info("seed.catalog_generated", extra=stats)
        else:
            log.info("seed.catalog_present")

        if settings.retriever == "chroma":
            activities = list(session.scalars(select(Activity)))
            index = ChromaIndex(settings.chroma_path, settings.embedding_model, settings.embedding_cache_dir)
            count = index.reindex(activities)
            log.info("seed.indexed", extra={"activities": count})

        if not args.no_demo:
            created = seed_demo(session, settings)
            log.info("seed.demo_conversations", extra={"conversations": created})


if __name__ == "__main__":
    main()
