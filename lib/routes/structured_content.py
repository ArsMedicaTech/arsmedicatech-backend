"""
Routes for structured content discovery.

Serves the replacement for the legacy ``custom_content`` microservice behind the
existing BFF at ``/api/content``.
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, Response, g, jsonify, request

from lib.services.auth_decorators import require_admin_or_provider, require_auth
from lib.services.structured_content_service import StructuredContentService
from settings import logger

structured_content_bp = Blueprint("structured_content", __name__)


def _service() -> StructuredContentService:
    """Factory for the structured content service."""
    return StructuredContentService()


def _run(coro: Any) -> Any:
    """Run an async coroutine from a sync Flask route."""
    return asyncio.run(coro)


def _list_items_response(items: List[Dict[str, Any]]) -> Tuple[Response, int]:
    """Wrap list results in the shape the Flutter client expects."""
    return jsonify({"items": items}), 200


@structured_content_bp.route("/api/content/clusters", methods=["GET"])
@require_auth
def list_clusters_route() -> Tuple[Response, int]:
    """Return cluster list with item counts (Mode 1)."""
    try:
        clusters = _run(_service().list_clusters())
        return jsonify({"clusters": clusters}), 200
    except Exception as exc:
        logger.error(f"Failed to list content clusters: {exc}", exc_info=True)
        return jsonify({"error": "Failed to load content clusters"}), 500


@structured_content_bp.route("/api/content/list", methods=["GET"])
@require_auth
def list_content_route() -> Tuple[Response, int]:
    """Browse content by cluster and/or tags (Mode 1)."""
    cluster = request.args.get("cluster") or None
    tags_param = request.args.get("tags", "")
    tags = [t.strip() for t in tags_param.split(",") if t.strip()] or None

    try:
        items = _run(_service().list_items(cluster=cluster, tags=tags))
        return _list_items_response(items)
    except Exception as exc:
        logger.error(f"Failed to list structured content: {exc}", exc_info=True)
        return jsonify({"error": "Failed to load content"}), 500


@structured_content_bp.route("/api/content/<item_id>", methods=["GET"])
@require_auth
def get_content_route(item_id: str) -> Tuple[Response, int]:
    """Return a full structured content record by id."""
    try:
        record = _run(_service().get_item(item_id))
        if not record:
            return jsonify({"error": "Content not found"}), 404
        return jsonify(record), 200
    except Exception as exc:
        logger.error(f"Failed to get structured content {item_id}: {exc}", exc_info=True)
        return jsonify({"error": "Failed to load content"}), 500


@structured_content_bp.route("/api/content/search", methods=["GET"])
@require_auth
def search_content_route() -> Tuple[Response, int]:
    """Proxy a text search to Typesense (Mode 2)."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    try:
        items, available = _run(_service().search(query))
        if not available:
            return jsonify({"items": [], "available": False}), 503
        return _list_items_response(items)
    except Exception as exc:
        logger.error(f"Failed to search structured content: {exc}", exc_info=True)
        return jsonify({"items": [], "available": False}), 503


@structured_content_bp.route("/api/content/similar", methods=["POST"])
@require_auth
def similar_content_route() -> Tuple[Response, int]:
    """Return semantically similar content using the caller's OpenAI key (Mode 3)."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip() if isinstance(data, dict) else ""
    if not query:
        return jsonify({"error": "Field 'query' is required"}), 400

    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    try:
        items, error = _run(_service().similar(query, str(user_id)))
        if error:
            # 409 signals a client-side configuration issue (missing/invalid key).
            return jsonify({"error": error}), 409
        return _list_items_response(items)
    except Exception as exc:
        logger.error(f"Failed similar content search for user={user_id}: {exc}", exc_info=True)
        return jsonify({"error": "Similar content search failed"}), 500


@structured_content_bp.route("/api/content/admin/reindex", methods=["POST"])
@require_auth
def reindex_content_route() -> Tuple[Response, int]:
    """
    Admin endpoint to re-derive and re-embed all structured content.

    In a future iteration this should be restricted to admin users.  For now it
    relies on ``require_auth`` and should be called by the deployment pipeline.
    """
    try:
        summary = _run(_service().reindex())
        return jsonify(summary), 200
    except Exception as exc:
        logger.error(f"Failed to reindex structured content: {exc}", exc_info=True)
        return jsonify({"error": "Reindex failed"}), 500


@structured_content_bp.route("/api/content/admin/ingest", methods=["POST"])
@require_auth
def ingest_content_route() -> Tuple[Response, int]:
    """
    Admin endpoint to import authored content from a legacy ``data.json``.

    Body: ``{"source": "/path/to/custom_content/data.json", "embed": false}``
    """
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json(silent=True) or {}
    source_path = data.get("source")
    if not source_path or not isinstance(source_path, str):
        return jsonify({"error": "Field 'source' is required"}), 400

    embed = bool(data.get("embed", False))

    try:
        summary = _run(_service().ingest_from_legacy(source_path, embed=embed))
        return jsonify(summary), 200
    except Exception as exc:
        logger.error(f"Failed to ingest structured content from {source_path}: {exc}", exc_info=True)
        return jsonify({"error": "Ingest failed"}), 500


def _item_payload() -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Response, int]]]:
    """Validate and normalize a single-item create/update request body."""
    if not request.is_json:
        return None, (jsonify({"error": "JSON body required"}), 400)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "JSON body must be an object"}), 400)

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, (jsonify({"error": "Field 'title' is required"}), 400)

    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return None, (jsonify({"error": "Field 'tags' must be an array of strings"}), 400)

    cluster = data.get("cluster")
    if not isinstance(cluster, str) or not cluster.strip():
        return None, (jsonify({"error": "Field 'cluster' is required"}), 400)

    content = data.get("content")
    if not isinstance(content, dict):
        return None, (jsonify({"error": "Field 'content' must be an object"}), 400)
    nodes = content.get("nodes")
    if not isinstance(nodes, list):
        return None, (jsonify({"error": "Field 'content.nodes' must be an array"}), 400)

    return {
        "title": title.strip(),
        "tags": tags,
        "cluster": cluster.strip(),
        "content": content,
    }, None


@structured_content_bp.route("/api/content/items", methods=["POST"])
@require_admin_or_provider
def create_content_item_route() -> Tuple[Response, int]:
    """Create a single authored content item."""
    payload, error = _item_payload()
    if error:
        return error

    try:
        record = _run(_service().save_item(None, **payload))
        return jsonify(record), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Failed to create structured content item: {exc}", exc_info=True)
        return jsonify({"error": "Failed to create content item"}), 500


@structured_content_bp.route("/api/content/items/<item_id>", methods=["PUT"])
@require_admin_or_provider
def update_content_item_route(item_id: str) -> Tuple[Response, int]:
    """Update a single authored content item by id."""
    payload, error = _item_payload()
    if error:
        return error

    try:
        record = _run(_service().save_item(item_id, **payload))
        return jsonify(record), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Failed to update structured content item {item_id}: {exc}", exc_info=True)
        return jsonify({"error": "Failed to update content item"}), 500
