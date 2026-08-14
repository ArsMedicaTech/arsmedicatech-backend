"""
Unit tests for the structured content REST routes.

Tests the route layer without requiring a running SurrealDB or Typesense by
mocking ``StructuredContentService``.
"""

import json
import sys
import types
from functools import wraps
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from flask import Flask, g


def _passthrough_decorator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    return wrapper


# Provide a minimal fake ``settings`` module before importing production code.
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

# Mock Sentry before any imports that might trigger it.
if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

# Bypass the real auth decorator so these tests can focus on route logic.
with patch(
    "lib.services.auth_decorators.require_auth", side_effect=_passthrough_decorator
):
    from lib.routes.structured_content import structured_content_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(structured_content_bp)

    @app.before_request
    def inject_user():
        g.user_id = "user-123"

    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestListClusters:
    def test_returns_clusters(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.list_clusters = AsyncMock(return_value=[
                {"cluster": "cardiovascular", "count": 3}
            ])

            response = client.get("/api/content/clusters")

        assert response.status_code == 200
        data = response.get_json()
        assert data["clusters"] == [{"cluster": "cardiovascular", "count": 3}]


class TestListContent:
    def test_returns_items(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.list_items = AsyncMock(return_value=[
                {
                    "id": "structured_content:bp",
                    "title": "BP",
                    "tags": ["cardio"],
                    "preview": "Blood pressure",
                }
            ])

            response = client.get("/api/content/list?cluster=cardiovascular&tags=cardio")

        assert response.status_code == 200
        data = response.get_json()
        assert data["items"][0]["title"] == "BP"
        service.list_items.assert_awaited_once_with(
            cluster="cardiovascular", tags=["cardio"]
        )


class TestGetContent:
    def test_returns_full_record(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.get_item = AsyncMock(return_value={
                "id": "structured_content:bp",
                "title": "BP",
                "content": {"nodes": []},
            })

            response = client.get("/api/content/structured_content:bp")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == "structured_content:bp"

    def test_missing_record_returns_404(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.get_item = AsyncMock(return_value=None)

            response = client.get("/api/content/nope")

        assert response.status_code == 404


class TestSearchContent:
    def test_returns_results_when_typesense_available(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.search = AsyncMock(return_value=(
                [{"id": "x", "title": "T", "tags": [], "preview": "p"}],
                True,
            ))

            response = client.get("/api/content/search?q=blood")

        assert response.status_code == 200
        data = response.get_json()
        assert data["items"][0]["title"] == "T"

    def test_returns_unavailable_when_typesense_down(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.search = AsyncMock(return_value=([], False))

            response = client.get("/api/content/search?q=blood")

        assert response.status_code == 503
        assert response.get_json()["available"] is False

    def test_requires_query(self, client):
        response = client.get("/api/content/search")
        assert response.status_code == 400


class TestSimilarContent:
    def test_returns_similar_items(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.similar = AsyncMock(return_value=(
                [{"id": "x", "title": "T", "tags": [], "preview": "p"}],
                None,
            ))

            response = client.post(
                "/api/content/similar",
                data=json.dumps({"query": "how to lower bp"}),
                content_type="application/json",
            )

        assert response.status_code == 200
        assert response.get_json()["items"][0]["title"] == "T"
        service.similar.assert_awaited_once_with("how to lower bp", "user-123")

    def test_returns_409_when_no_key(self, client):
        expected_msg = "OpenAI API key not configured."
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.similar = AsyncMock(return_value=([], expected_msg))

            response = client.post(
                "/api/content/similar",
                data=json.dumps({"query": "x"}),
                content_type="application/json",
            )

        assert response.status_code == 409
        assert expected_msg in response.get_json()["error"]

    def test_requires_query(self, client):
        response = client.post(
            "/api/content/similar",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestReindexRoute:
    def test_returns_summary(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.reindex = AsyncMock(return_value={
                "embedded": 2, "skipped": 5, "total": 7, "typesense": {}
            })

            response = client.post("/api/content/admin/reindex")

        assert response.status_code == 200
        data = response.get_json()
        assert data["embedded"] == 2
        assert data["skipped"] == 5


class TestIngestRoute:
    def test_requires_source(self, client):
        response = client.post(
            "/api/content/admin/ingest",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_runs_ingest(self, client):
        with patch(
            "lib.routes.structured_content.StructuredContentService"
        ) as mock_service_cls:
            service = mock_service_cls.return_value
            service.ingest_from_legacy = AsyncMock(return_value={"imported": 3})

            response = client.post(
                "/api/content/admin/ingest",
                data=json.dumps({"source": "/tmp/data.json"}),
                content_type="application/json",
            )

        assert response.status_code == 200
        assert response.get_json()["imported"] == 3
        service.ingest_from_legacy.assert_awaited_once_with("/tmp/data.json", embed=False)
