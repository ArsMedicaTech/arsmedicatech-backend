"""
Unit tests for the LLM API trace logging service.
"""

import sys
import types
from unittest.mock import MagicMock

# Provide a minimal fake settings module so the service can import.
if "settings" not in sys.modules:
    fake_settings = types.ModuleType("settings")
    fake_settings.logger = MagicMock()
    # Include the attributes other unit tests expect when this module is imported first.
    fake_settings.FHIR_GATEWAY_URL = "http://fake-hapi/fhir"
    fake_settings.FHIR_BASE_URL = "http://fake-hapi/fhir"
    fake_settings.KEYCLOAK_BASE_URL = "http://fake-keycloak"
    fake_settings.KEYCLOAK_REALM = "test"
    fake_settings.KEYCLOAK_CLIENT_ID = "test-client"
    fake_settings.KEYCLOAK_CLIENT_SECRET = "test-secret"
    fake_settings.SURREALDB_URL = "http://localhost:8000"
    fake_settings.SURREALDB_NAMESPACE = "test"
    fake_settings.SURREALDB_DATABASE = "test"
    fake_settings.SURREALDB_USER = "test"
    fake_settings.SURREALDB_PASS = "test"
    sys.modules["settings"] = fake_settings

# Avoid pulling in the real Sentry SDK in the test environment.
if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

# Stub out the SurrealDB controller so tests don't need a running database.
if "amt_nano.db.surreal" not in sys.modules:
    fake_surreal = types.ModuleType("amt_nano.db.surreal")
    fake_surreal.DbController = MagicMock
    sys.modules["amt_nano.db.surreal"] = fake_surreal

import pytest

from lib.services.llm_trace_service import (
    LLMTraceLogger,
    build_trace_context,
    hash_tool_definitions,
    scrub_sensitive,
)


def test_scrub_sensitive_redacts_deny_list_keys():
    payload = {
        "messages": [
            {"role": "user", "content": "hello"},
        ],
        "extra_headers": {"x-user-pw": "super-secret", "authorization": "Bearer t"},
        "api_key": "sk-abc",
        "password": "pwd",
        "token": "tok",
        "safe": "visible",
    }
    scrubbed = scrub_sensitive(payload)
    assert scrubbed["extra_headers"]["x-user-pw"] == "***"
    assert scrubbed["extra_headers"]["authorization"] == "***"
    assert scrubbed["api_key"] == "***"
    assert scrubbed["password"] == "***"
    assert scrubbed["token"] == "***"
    assert scrubbed["safe"] == "visible"
    assert scrubbed["messages"][0]["content"] == "hello"


def test_hash_tool_definitions_is_stable():
    defs = [
        {"function": {"name": "rag", "description": "lookup"}},
        {"function": {"name": "echo", "description": "repeat"}},
    ]
    h1 = hash_tool_definitions(defs)
    h2 = hash_tool_definitions(defs)
    assert h1 == h2
    assert len(h1) == 32


def test_build_trace_context_generates_trace_id():
    fake_db = MagicMock()
    ctx = build_trace_context(fake_db, thread_id="llm_chat_thread:abc", user_id="user:123")
    assert ctx["db_controller"] is fake_db
    assert ctx["thread_id"] == "llm_chat_thread:abc"
    assert ctx["user_id"] == "user:123"
    assert ctx["turn_index"] == 0
    assert isinstance(ctx["trace_id"], str) and ctx["trace_id"]


def test_log_pre_call_returns_record_id():
    fake_db = MagicMock()
    fake_db.create.return_value = {"id": "llm_api_trace:abc123"}

    logger = LLMTraceLogger(fake_db)
    record_id = logger.log_pre_call(
        trace_id="trace-1",
        thread_id="llm_chat_thread:abc",
        user_id="user:123",
        turn_index=0,
        model="gpt-5-nano",
        messages=[{"role": "system", "content": "You are helpful."}],
        tool_definitions=[{"function": {"name": "rag"}}],
        response_format=None,
    )

    assert record_id == "llm_api_trace:abc123"
    fake_db.create.assert_called_once()
    call_args = fake_db.create.call_args[0]
    assert call_args[0] == "llm_api_trace"
    payload = call_args[1]
    assert payload["trace_id"] == "trace-1"
    assert payload["model"] == "gpt-5-nano"
    assert payload["messages"][0]["role"] == "system"
    assert payload["tool_names"] == ["rag"]
    assert payload["response_format"] is None


def test_log_post_call_merges_response_data():
    fake_db = MagicMock()
    fake_db.create.return_value = {"id": "llm_api_trace:abc123"}

    logger = LLMTraceLogger(fake_db)
    record_id = logger.log_pre_call(
        trace_id="trace-1",
        thread_id="llm_chat_thread:abc",
        user_id="user:123",
        turn_index=0,
        model="gpt-5-nano",
        messages=[],
        tool_definitions=[],
        response_format=None,
    )

    completion = MagicMock()
    completion.usage.model_dump.return_value = {"prompt_tokens": 10, "completion_tokens": 5}
    message = MagicMock()
    message.content = "Hi there"
    message.tool_calls = None
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = message
    completion.choices = [choice]

    logger.log_post_call(record_id, completion=completion, duration_ms=123)

    fake_db.query.assert_called_once()
    query, params = fake_db.query.call_args[0]
    assert "MERGE" in query
    assert params["tb"] == "llm_api_trace"
    assert params["rid"] == "abc123"
    assert params["data"]["content"] == "Hi there"
    assert params["data"]["duration_ms"] == 123


def test_log_post_call_exception_merges_error():
    fake_db = MagicMock()
    fake_db.create.return_value = {"id": "llm_api_trace:abc123"}

    logger = LLMTraceLogger(fake_db)
    record_id = logger.log_pre_call(
        trace_id="trace-1",
        thread_id="llm_chat_thread:abc",
        user_id="user:123",
        turn_index=0,
        model="gpt-5-nano",
        messages=[],
        tool_definitions=[],
        response_format=None,
    )

    logger.log_post_call_exception(record_id, exc=RuntimeError("boom"), duration_ms=42)

    fake_db.query.assert_called_once()
    _query, params = fake_db.query.call_args[0]
    assert "RuntimeError" in params["data"]["error"]
    assert params["data"]["duration_ms"] == 42
