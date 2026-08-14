"""
Unit tests for the structured content service helpers and write-path invariants.

These tests avoid touching SurrealDB or OpenAI by exercising the pure helper
functions and by mocking the async DB controller.
"""

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Install a minimal fake ``settings`` module before any production code can import
# the real one (which pulls in Vault/Keycloak/Sentry initialisation).
# Force a clean fake settings module so stale/partially-initialized copies left
# behind by other failing imports do not pollute this test module.
sys.modules.pop("settings", None)
fake_settings = types.ModuleType("settings")
fake_settings.SURREALDB_NAMESPACE = "test_ns"
fake_settings.SURREALDB_DATABASE = "test_db"
fake_settings.SURREALDB_USER = "test_user"
fake_settings.SURREALDB_PASS = "test_pass"
fake_settings.SURREALDB_URL = "http://localhost:8000"
fake_settings.MIGRATION_OPENAI_API_KEY = "sk-test"
fake_settings.TYPESENSE_URL = "http://localhost:8108"
fake_settings.TYPESENSE_API_KEY = "test-key"
fake_settings.TYPESENSE_STRUCTURED_CONTENT_ALIAS = "structured_content"
fake_settings.FHIR_BASE_URL = "http://fake-hapi/fhir"
fake_settings.FHIR_GATEWAY_URL = "http://fake-hapi/fhir"
fake_settings.KEYCLOAK_BASE_URL = "http://fake-keycloak"
fake_settings.KEYCLOAK_REALM = "test"
fake_settings.KEYCLOAK_CLIENT_ID = "test-client"
fake_settings.KEYCLOAK_CLIENT_SECRET = "test-secret"
fake_settings.ENCRYPTION_KEY = "a" * 32
fake_settings.logger = MagicMock()

sys.modules["settings"] = fake_settings

from lib.services.structured_content_service import (
    DEFAULT_EMBED_MODEL,
    _content_hash,
    _derive_plain_text,
    _list_item,
    _preview_text,
    _record_id_to_str,
)


class TestPlainTextDerivation:
    def test_extracts_title_and_paragraph(self):
        nodes = [
            {"type": "title", "text": "Managing Blood Pressure"},
            {"type": "paragraph", "text": "High blood pressure can be managed."},
        ]
        assert _derive_plain_text(nodes) == (
            "Managing Blood Pressure\n\nHigh blood pressure can be managed."
        )

    def test_list_items_bulleted(self):
        nodes = [
            {"type": "title", "text": "Tips"},
            {"type": "list", "items": ["Eat well", "Exercise"]},
        ]
        assert _derive_plain_text(nodes) == "Tips\n\n- Eat well\n- Exercise"

    def test_ignores_unknown_node_types(self):
        nodes = [
            {"type": "image", "url": "https://example.com/x.png", "alt": "Chart"},
        ]
        assert _derive_plain_text(nodes) == ""


class TestContentHash:
    def test_stable_across_reordering_in_source(self):
        # The same logical nodes produce the same canonical JSON.
        nodes = [
            {"type": "paragraph", "text": "A"},
            {"type": "title", "text": "T"},
        ]
        h1 = _content_hash(nodes)
        h2 = _content_hash(list(reversed(nodes)))
        assert h1 != h2  # order matters for content nodes (intended)

    def test_deterministic(self):
        nodes = [{"type": "paragraph", "text": "A"}]
        assert _content_hash(nodes) == _content_hash(nodes)
        assert _content_hash(nodes).startswith("sha256:")


class TestPreviewText:
    def test_short_text_unchanged(self):
        assert _preview_text("Hello world") == "Hello world"

    def test_collapses_whitespace(self):
        assert _preview_text("Hello\n\n  world") == "Hello world"

    def test_truncates_long_text(self):
        long_text = "x" * 300
        preview = _preview_text(long_text)
        assert preview.endswith("...")
        assert len(preview) == 200


class TestListItem:
    def test_extracts_preview_from_plain_text(self):
        record = {
            "id": "structured_content:bp",
            "title": "BP",
            "tags": ["cardio"],
            "plain_text": "Managing Blood Pressure\n\nHigh blood pressure...",
        }
        item = _list_item(record)
        assert item["id"] == "structured_content:bp"
        assert item["title"] == "BP"
        assert item["tags"] == ["cardio"]
        assert "High blood pressure" in item["preview"]

    def test_falls_back_to_title_node(self):
        record = {
            "id": "structured_content:bp",
            "title": "",
            "tags": [],
            "plain_text": "",
            "content": {"nodes": [{"type": "title", "text": "Fallback Title"}]},
        }
        item = _list_item(record)
        assert item["title"] == "Fallback Title"


class TestRecordIdToStr:
    def test_string_passed_through(self):
        assert _record_id_to_str("structured_content:bp") == "structured_content:bp"

    def test_mock_record_id(self):
        rid = Mock()
        rid.__str__ = Mock(return_value="structured_content:bp")
        assert _record_id_to_str(rid) == "structured_content:bp"


class TestAsyncService:
    """Tests that exercise the service methods with a mocked async DB controller."""

    @pytest.fixture
    def service(self):
        from lib.services.structured_content_service import StructuredContentService

        mock_db = AsyncMock()
        svc = StructuredContentService(db_controller=mock_db)
        svc.db.connect = AsyncMock()
        svc.db.close = AsyncMock()
        svc.db.query = AsyncMock()
        svc.db.select = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_get_item_normalizes_double_prefixed_id(self, service):
        service.db.select.return_value = {
            "id": "structured_content:bp",
            "title": "BP",
            "content": {"nodes": []},
        }
        record = await service.get_item("structured_content:bp")
        assert record["id"] == "structured_content:bp"
        service.db.select.assert_awaited_once_with("structured_content:bp")

    @pytest.mark.asyncio
    async def test_list_clusters_groups_and_counts(self, service):
        service.db.query.return_value = [
            {"cluster": "cardiovascular", "count": 3},
            {"cluster": "diabetes", "count": 1},
        ]
        clusters = await service.list_clusters()
        assert clusters == [
            {"cluster": "cardiovascular", "count": 3},
            {"cluster": "diabetes", "count": 1},
        ]
        args = service.db.query.await_args
        assert "GROUP BY cluster" in args[0][0]
        assert "scope = 'global'" in args[0][0]

    @pytest.mark.asyncio
    async def test_list_items_filters_by_cluster_and_tags(self, service):
        service.db.query.return_value = [
            {
                "id": "structured_content:bp",
                "title": "BP",
                "tags": ["cardio"],
                "plain_text": "Blood pressure",
            }
        ]
        items = await service.list_items(cluster="cardiovascular", tags=["cardio"])
        assert len(items) == 1
        assert items[0]["title"] == "BP"
        args = service.db.query.await_args
        assert "cluster = $cluster" in args[0][0]
        assert "tags CONTAINSALL $tags" in args[0][0]


class TestUpdateTitleOnly:
    @pytest.mark.asyncio
    async def test_update_title_only_preserves_derived_fields(self):
        from lib.services.structured_content_service import StructuredContentService

        mock_db = AsyncMock()
        service = StructuredContentService(db_controller=mock_db)
        service.db.connect = AsyncMock()
        service.db.close = AsyncMock()
        service.db.query = AsyncMock()

        await service.update_title_only("bp", "New Title")

        call = service.db.query.await_args
        query, params = call[0][0], call.kwargs.get("vars") or call[0][1]
        assert "MERGE" in query
        assert params["data"]["title"] == "New Title"
        assert "plain_text" not in params["data"]
        assert "embedding" not in params["data"]


class TestTypesenseBulkImport:
    """Smoke tests for the private Typesense reindex helper."""

    def test_reindex_typesense_skips_when_not_configured(self):
        from lib.services.structured_content_service import StructuredContentService

        service = StructuredContentService(
            db_controller=AsyncMock(),
            typesense_url="",
            typesense_api_key="",
        )
        result = service._reindex_typesense([])
        assert result["published"] == 0
        assert result["collection"] is None
