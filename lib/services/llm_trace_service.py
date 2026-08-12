"""
LLM API trace logging service.

Persists detailed request/response metadata for every LLM API round-trip to the
existing SurrealDB database (table: llm_api_trace) so that payloads stay co-located
with the chat threads they belong to.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from amt_nano.db.surreal import DbController

from settings import logger


def _scrub_value(value: Any, deny_keys: Sequence[str]) -> Any:
    """Recursively redact sensitive keys from a JSON-like structure."""
    if isinstance(value, Mapping):
        return {
            key: "***" if key.lower() in deny_keys else _scrub_value(val, deny_keys)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item, deny_keys) for item in value]
    return value


# Keys that must never be persisted in a trace row.
SENSITIVE_LOG_KEYS = frozenset(
    ("api_key", "x-user-pw", "authorization", "password", "token")
)


def scrub_sensitive(data: Any) -> Any:
    """Return a copy of *data* with sensitive keys redacted."""
    return _scrub_value(data, SENSITIVE_LOG_KEYS)


def _serialize_for_hash(obj: Any) -> str:
    """Serialize a value to a canonical JSON string suitable for hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, default=str)


def hash_tool_definitions(tool_definitions: Sequence[Any]) -> str:
    """Return a stable MD5 hash of the full tool definitions."""
    return hashlib.md5(
        _serialize_for_hash(tool_definitions).encode("utf-8")
    ).hexdigest()


class LLMTraceLogger:
    """
    Writes two-phase LLM API traces to SurrealDB:
      1. Pre-call INSERT captures the exact outbound payload.
      2. Post-call MERGE adds response metadata or exception details.
    """

    def __init__(self, db_controller: DbController) -> None:
        self.db = db_controller

    def log_pre_call(
        self,
        *,
        trace_id: str,
        thread_id: Optional[str],
        user_id: Optional[str],
        turn_index: int,
        model: str,
        messages: Sequence[Any],
        tool_definitions: Sequence[Any],
        response_format: Optional[Any],
    ) -> Optional[str]:
        """
        Insert a pre-call trace row.

        :return: The created SurrealDB record ID, or None if logging failed.
        """
        tool_names: List[Optional[str]] = [
            tool_def.get("function", {}).get("name")
            for tool_def in tool_definitions
            if isinstance(tool_def, dict)
        ]
        tool_names = [name for name in tool_names if name]

        payload: Dict[str, Any] = {
            "trace_id": trace_id,
            "thread_id": thread_id,
            "user_id": user_id,
            "turn_index": turn_index,
            "model": model,
            "messages": scrub_sensitive(messages),
            "tool_names": tool_names or None,
            "tool_definitions_hash": hash_tool_definitions(tool_definitions),
            "response_format": (
                _serialize_for_hash(response_format) if response_format is not None else None
            ),
            "request_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            result = self.db.create("llm_api_trace", payload)
            if isinstance(result, dict):
                record_id = result.get("id")
                if record_id:
                    return str(record_id)
            # Some SurrealDB drivers return a list of results.
            if isinstance(result, list) and result:
                record_id = result[0].get("id") if isinstance(result[0], dict) else None
                if record_id:
                    return str(record_id)
        except Exception as e:
            logger.warning(f"Failed to write pre-call LLM trace: {e}")
        return None

    def _merge(self, record_id: str, data: Dict[str, Any]) -> None:
        """MERGE post-call fields into the existing trace row."""
        # SurrealDB's MERGE sets explicit None values to NONE, so strip unset fields.
        cleaned = {k: v for k, v in data.items() if v is not None}
        if not cleaned:
            return

        tb, _, rid = record_id.partition(":")
        if not tb or not rid:
            logger.warning(f"Cannot merge LLM trace: invalid record_id {record_id}")
            return

        try:
            self.db.query(
                "UPDATE type::thing($tb, $rid) MERGE $data",
                {"tb": tb, "rid": rid, "data": cleaned},
            )
        except Exception as e:
            logger.warning(f"Failed to write post-call LLM trace: {e}")

    def log_post_call(
        self,
        record_id: Optional[str],
        *,
        completion: Any,
        duration_ms: int,
    ) -> None:
        """Merge successful response metadata into the pre-call trace row."""
        if not record_id:
            return

        try:
            choice = completion.choices[0]
            message = choice.message

            tool_calls: Optional[List[Dict[str, Any]]] = None
            if message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in message.tool_calls
                ]

            usage: Optional[Dict[str, Any]] = None
            if completion.usage is not None:
                usage = (
                    completion.usage.model_dump()
                    if hasattr(completion.usage, "model_dump")
                    else dict(completion.usage)
                )

            self._merge(
                record_id,
                {
                    "finish_reason": choice.finish_reason,
                    "content": message.content,
                    "tool_calls": tool_calls,
                    "usage": scrub_sensitive(usage),
                    "duration_ms": duration_ms,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to serialize post-call LLM trace: {e}")

    def log_post_call_exception(
        self,
        record_id: Optional[str],
        *,
        exc: BaseException,
        duration_ms: int,
    ) -> None:
        """Merge exception details into the pre-call trace row."""
        if not record_id:
            return
        self._merge(
            record_id,
            {
                "error": repr(exc),
                "duration_ms": duration_ms,
            },
        )


def build_trace_context(
    db_controller: DbController,
    *,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    """Convenience helper to assemble the trace context passed into LLMAgent.complete()."""
    return {
        "db_controller": db_controller,
        "trace_id": trace_id or str(uuid.uuid4()),
        "thread_id": thread_id,
        "user_id": user_id,
        "turn_index": turn_index,
    }
