"""
ICD autocoder proxy for the Flutter web app.

Forwards suggestion requests to the nanoservice autocoder and persists feedback
telemetry in SurrealDB.
"""

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Blueprint, Response, g, jsonify, request

from amt_nano.db.surreal import DbController
from lib.services.auth_decorators import require_auth
from lib.services.redis_client import get_redis_connection
from settings import (
    ICD_AUTOCODER_FEEDBACK_TABLE,
    ICD_AUTOCODER_RATE_LIMIT,
    ICD_AUTOCODER_RATE_WINDOW,
    ICD_AUTOCODER_TIMEOUT,
    ICD_AUTOCODER_URL,
    logger,
)

icd_autocoder_bp = Blueprint("icd_autocoder", __name__)

_feedback_table: str = ICD_AUTOCODER_FEEDBACK_TABLE or "icd_feedback"

# In-process fallback used when Redis is not available.
_rate_limit_memory: Dict[str, List[float]] = {}


def _note_hash(note_text: str) -> str:
    """Return a short SHA-256 hash of the note text; log this, not the text."""
    return hashlib.sha256(note_text.encode("utf-8")).hexdigest()[:16]


def _check_rate_limit(user_id: str) -> Tuple[bool, Optional[int]]:
    """
    Sliding-window rate limit per user. Tries Redis first, then falls back to
    an in-process dictionary.
    """
    window = ICD_AUTOCODER_RATE_WINDOW or 60
    limit = ICD_AUTOCODER_RATE_LIMIT or 60
    key = f"icd_autocoder:{user_id}:requests"
    now = time.time()
    cutoff = now - window

    try:
        redis = get_redis_connection()
        redis.zremrangebyscore(key, 0, cutoff)
        current = redis.zcard(key)
        if current >= limit:
            oldest = redis.zrange(key, 0, 0, withscores=True)
            retry_after = int(window - (now - oldest[0][1])) if oldest else window
            return False, retry_after
        member = f"{now}:{uuid.uuid4().hex}"
        redis.zadd(key, {member: now})
        redis.expire(key, window)
        return True, None
    except Exception as exc:
        logger.warning(f"Redis rate-limit check failed for {user_id}; using in-process: {exc}")
        window_calls = _rate_limit_memory.setdefault(user_id, [])
        # Prune old calls
        while window_calls and window_calls[0] < cutoff:
            window_calls.pop(0)
        if len(window_calls) >= limit:
            retry_after = int(window - (now - window_calls[0]))
            return False, retry_after
        window_calls.append(now)
        return True, None


def _feedback_record_id(user_id: str, data: Dict[str, Any]) -> str:
    """Deterministic record id so feedback can be safely merged."""
    payload = (
        f"{user_id}:"
        f"{data.get('span_text','')}:",
        f"{data.get('candidate_code','')}:",
        f"{data.get('system','')}:",
        f"{data.get('sentence','')}",
    )
    return hashlib.sha256("".join(payload).encode("utf-8")).hexdigest()[:32]


def _span_count_from_response(body: bytes) -> int:
    """Best-effort span count from the autocoder JSON response."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("spans"), list):
                return len(parsed["spans"])
            return parsed.get("span_count", 0) or 0
    except Exception:
        pass
    return 0


@icd_autocoder_bp.route("/api/icd/suggest", methods=["POST"])
@require_auth
def icd_suggest_route() -> Tuple[Response, int]:
    """Forward a note to the ICD autocoder and return the v2 response unchanged."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json(silent=True) or {}
    note_text = data.get("note_text")
    if not isinstance(note_text, str) or not note_text.strip():
        return jsonify({"error": "note_text is required"}), 400

    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    allowed, retry_after = _check_rate_limit(str(user_id))
    if not allowed:
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        return (
            jsonify({"error": "Rate limit exceeded", "code": "rate_limit_exceeded"}),
            429,
            headers,
        )

    if not ICD_AUTOCODER_URL:
        logger.error("ICD_AUTOCODER_URL is not configured")
        return (
            jsonify(
                {
                    "error": "ICD autocoder is not configured",
                    "code": "icd_autocoder_unavailable",
                }
            ),
            503,
        )

    note_hash = _note_hash(note_text)
    try:
        resp = requests.post(
            ICD_AUTOCODER_URL,
            json={"note_text": note_text},
            timeout=ICD_AUTOCODER_TIMEOUT or 10,
        )
    except requests.Timeout:
        logger.warning(f"ICD autocoder timeout for user={user_id} note_hash={note_hash}")
        return (
            jsonify(
                {
                    "error": "ICD autocoder timed out",
                    "code": "icd_autocoder_unavailable",
                }
            ),
            503,
        )
    except requests.RequestException as exc:
        logger.warning(f"ICD autocoder request failed for user={user_id}: {exc}")
        return (
            jsonify(
                {
                    "error": "ICD autocoder unavailable",
                    "code": "icd_autocoder_unavailable",
                }
            ),
            503,
        )

    if resp.status_code >= 500:
        logger.warning(
            f"ICD autocoder 5xx for user={user_id} "
            f"note_hash={note_hash} status={resp.status_code}"
        )
        return (
            jsonify(
                {
                    "error": "ICD autocoder unavailable",
                    "code": "icd_autocoder_unavailable",
                }
            ),
            503,
        )

    span_count = _span_count_from_response(resp.content)
    logger.info(
        f"ICD suggest user={user_id} note_hash={note_hash} "
        f"span_count={span_count} upstream_status={resp.status_code}"
    )

    out_headers = {}
    content_type = resp.headers.get("Content-Type")
    if content_type:
        out_headers["Content-Type"] = content_type
    return Response(resp.content, status=resp.status_code, headers=out_headers)


@icd_autocoder_bp.route("/api/icd/feedback", methods=["POST"])
@require_auth
def icd_feedback_route() -> Tuple[Response, int]:
    """Persist rejection/acceptance telemetry to SurrealDB."""
    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json(silent=True) or {}
    required = {"span_text", "candidate_code", "system", "sentence", "accepted"}
    missing = sorted(required - set(data.keys()))
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    record_id = _feedback_record_id(str(user_id), data)
    payload: Dict[str, Any] = {
        "user_id": str(user_id),
        "span_text": data["span_text"],
        "candidate_code": data["candidate_code"],
        "system": data["system"],
        "sentence": data["sentence"],
        "accepted": bool(data["accepted"]),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    db = DbController()
    db.connect()
    try:
        # UPSERT with MERGE so existing sibling fields are preserved.
        db.query(
            "UPSERT type::thing($tb, $rid) MERGE $data",
            {"tb": _feedback_table, "rid": record_id, "data": payload},
        )
    except Exception as exc:
        logger.error(f"Failed to persist ICD feedback for user={user_id}: {exc}")
        return jsonify({"error": "Failed to persist feedback"}), 500
    finally:
        db.close()

    logger.info(f"ICD feedback persisted user={user_id} record={record_id}")
    return jsonify({"ok": True}), 201
