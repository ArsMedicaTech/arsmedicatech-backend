"""
Structured content migration script.

1. Initializes the ``structured_content`` SurrealDB table and indexes.
2. Imports authored items from a legacy ``custom_content/data.json``.
3. Re-derives and embeds all records, then publishes them to Typesense.

This should be run once when the feature is deployed, after the legacy
``custom_content`` service has been stopped but before it is removed from
Kubernetes/apphosting config.
"""

import asyncio
import os
import sys
from argparse import ArgumentParser

# Ensure project root is importable when run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from lib.services.structured_content_service import StructuredContentService
from settings import logger


def init_structured_content() -> None:
    """Create the SurrealDB table and indexes."""
    service = StructuredContentService()
    try:
        asyncio.run(service.init_schema())
    except Exception as exc:
        logger.error(f"Failed to initialize structured_content schema: {exc}")
        raise


def ingest_structured_content(source_path: str, embed: bool = False) -> None:
    """Import legacy ``custom_content/data.json`` into SurrealDB."""
    service = StructuredContentService()
    try:
        summary = asyncio.run(service.ingest_from_legacy(source_path, embed=embed))
        logger.info(f"Ingest summary: {summary}")
    except Exception as exc:
        logger.error(f"Failed to ingest structured content from {source_path}: {exc}")
        raise


def reindex_structured_content() -> None:
    """Re-derive and re-embed all records, then publish to Typesense."""
    service = StructuredContentService()
    try:
        summary = asyncio.run(service.reindex())
        logger.info(f"Reindex summary: {summary}")
    except Exception as exc:
        logger.error(f"Failed to reindex structured content: {exc}")
        raise


def main() -> None:
    parser = ArgumentParser(description="Structured content migration.")
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Create the SurrealDB table and indexes.",
    )
    parser.add_argument(
        "--ingest",
        metavar="PATH",
        help="Path to the legacy custom_content/data.json file.",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-derive fields, embed, and publish to Typesense.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Embed immediately during ingest (default: defer to --reindex).",
    )
    args = parser.parse_args()

    if args.init_schema:
        init_structured_content()
    if args.ingest:
        ingest_structured_content(args.ingest, embed=args.embed)
    if args.reindex:
        reindex_structured_content()

    if not (args.init_schema or args.ingest or args.reindex):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
