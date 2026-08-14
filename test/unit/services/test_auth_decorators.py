"""
Unit tests for auth decorator helpers.

These tests avoid touching live Keycloak/SurrealDB by mocking the underlying
``UserService`` and ``require_auth``.
"""

import sys
import types
from functools import wraps
from unittest.mock import MagicMock, Mock, patch

import pytest
from flask import Flask, Response, g, jsonify

# Install a minimal fake ``settings`` module before importing production code.
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

if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

from lib.services.auth_decorators import require_admin_or_provider


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = "test-secret"

    @app.route("/test", methods=["GET"])
    @require_admin_or_provider
    def protected():
        return jsonify({"ok": True}), 200

    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestRequireAdminOrProvider:
    def _mock_user(self, role):
        user = Mock()
        user.role = role
        user.is_admin.return_value = role == "admin"
        user.is_provider.return_value = role in ("admin", "provider")
        return user

    def _mock_require_auth(self, result=None):
        """Return a fake ``require_auth`` decorator that yields ``result``."""
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                if result is None:
                    return f(*args, **kwargs)
                return result
            return wrapper
        return decorator

    def test_allows_admin_user(self, app, client):
        user_service = Mock()
        user_service.connect = Mock()
        user_service.close = Mock()
        user_service.get_user_by_id.return_value = self._mock_user("admin")

        with patch(
            "lib.services.auth_decorators.require_auth",
            side_effect=self._mock_require_auth(None),
        ), patch(
            "lib.services.auth_decorators.UserService", return_value=user_service
        ):
            with app.test_request_context("/test", method="GET"):
                g.user_session = Mock(user_id="admin-1")
                response = client.get("/test")

        assert response.status_code == 200
        assert response.get_json()["ok"] is True

    def test_allows_provider_user(self, app, client):
        user_service = Mock()
        user_service.connect = Mock()
        user_service.close = Mock()
        user_service.get_user_by_id.return_value = self._mock_user("provider")

        with patch(
            "lib.services.auth_decorators.require_auth",
            side_effect=self._mock_require_auth(None),
        ), patch(
            "lib.services.auth_decorators.UserService", return_value=user_service
        ):
            with app.test_request_context("/test", method="GET"):
                g.user_session = Mock(user_id="provider-1")
                response = client.get("/test")

        assert response.status_code == 200
        assert response.get_json()["ok"] is True

    def test_rejects_patient_with_403(self, app, client):
        user_service = Mock()
        user_service.connect = Mock()
        user_service.close = Mock()
        user_service.get_user_by_id.return_value = self._mock_user("patient")

        with patch(
            "lib.services.auth_decorators.require_auth",
            side_effect=self._mock_require_auth(None),
        ), patch(
            "lib.services.auth_decorators.UserService", return_value=user_service
        ):
            with app.test_request_context("/test", method="GET"):
                g.user_session = Mock(user_id="patient-1")
                response = client.get("/test")

        assert response.status_code == 403
        assert "provider" in response.get_json()["error"].lower()

    def test_rejects_unauthenticated_with_403(self, app, client):
        user_service = Mock()
        user_service.connect = Mock()
        user_service.close = Mock()

        with patch(
            "lib.services.auth_decorators.require_auth",
            side_effect=self._mock_require_auth(
                (Response("Authentication required"), 401)
            ),
        ), patch(
            "lib.services.auth_decorators.UserService", return_value=user_service
        ):
            response = client.get("/test")

        assert response.status_code == 403

    def test_rejects_missing_user_session_with_403(self, app, client):
        user_service = Mock()
        user_service.connect = Mock()
        user_service.close = Mock()

        with patch(
            "lib.services.auth_decorators.require_auth",
            side_effect=self._mock_require_auth(None),
        ), patch(
            "lib.services.auth_decorators.UserService", return_value=user_service
        ):
            with app.test_request_context("/test", method="GET"):
                if hasattr(g, "user_session"):
                    del g.user_session
                response = client.get("/test")

        assert response.status_code == 403
