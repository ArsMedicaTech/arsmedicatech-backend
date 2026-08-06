"""
Unit tests for the Oscar provider identity linking admin endpoints.
"""

import json
import sys
import types
from unittest.mock import MagicMock, Mock, patch

if "settings" not in sys.modules:
    fake_settings = types.ModuleType("settings")
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
    fake_settings.logger = MagicMock()
    sys.modules["settings"] = fake_settings

if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

import pytest
from flask import Flask, g

from lib.models.user.user import User
from lib.routes.admin_provider_identity import (
    OSCAR_PROVIDER_SYSTEM,
    get_oscar_provider_candidates_route,
    link_oscar_provider_route,
)


@pytest.fixture
def admin_request_context():
    app = Flask(__name__)
    with app.test_request_context():
        g.user_role = "admin"
        g.user_id = "admin-1"
        yield


@pytest.fixture
def provider_user():
    return User(
        id="user-123",
        username="dr_jones",
        email="jones@example.com",
        role="provider",
        fhir_practitioner_id="pr-abc",
        first_name="Jane",
        last_name="Jones",
    )


@pytest.fixture
def patient_user():
    return User(
        id="user-456",
        username="pat_doe",
        email="pat@example.com",
        role="patient",
        fhir_patient_id="p-xyz",
    )


def _make_response(status_code: int, json_data=None) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
        resp.text = json.dumps(json_data)
    else:
        resp.text = ""
    return resp


def _amt_resource(with_oscar_id: bool = False) -> dict:
    resource = {
        "resourceType": "Practitioner",
        "id": "pr-abc",
        "active": True,
        "name": [{"family": "Jones", "given": ["Jane"]}],
    }
    if with_oscar_id:
        resource["identifier"] = [
            {"system": OSCAR_PROVIDER_SYSTEM, "value": "100001"}
        ]
    return resource


def _orphan_resource(oscar_provider_no: str = "100001") -> dict:
    return {
        "resourceType": "Practitioner",
        "id": "1003",
        "active": True,
        "identifier": [
            {"system": OSCAR_PROVIDER_SYSTEM, "value": oscar_provider_no},
            {"system": "http://hl7.org/fhir/sid/ca-bc-billing", "value": "A1234"},
        ],
        "telecom": [{"system": "email", "value": "jones@example.com"}],
    }


class TestLinkOscarProvider:
    @pytest.fixture(autouse=True)
    def patch_user(self, monkeypatch, provider_user):
        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._get_user_by_id",
            lambda uid: provider_user if uid == provider_user.id else None,
        )

    def test_requires_admin(self, admin_request_context):
        g.user_role = "provider"
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "provider"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 403
            assert response.get_json()["error"] == "Admin role required"

    def test_rejects_missing_oscar_provider_no(
        self, admin_request_context
    ):
        with Flask(__name__).test_request_context(method="POST", json={}):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 400
            assert response.get_json()["error"] == "oscar_provider_no is required"

    def test_rejects_nonexistent_user(
        self, admin_request_context, monkeypatch
    ):
        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._get_user_by_id", lambda _uid: None
        )
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 404

    def test_rejects_patient_role(
        self, admin_request_context, monkeypatch, patient_user
    ):
        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._get_user_by_id",
            lambda _uid: patient_user,
        )
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-456")
            assert status == 400
            assert response.get_json()["error"] == "User must be a provider"

    def test_rejects_missing_fhir_practitioner_id(
        self, admin_request_context, monkeypatch, provider_user
    ):
        provider_user.fhir_practitioner_id = None
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 400
            assert response.get_json()["error"] == "Provider has no fhir_practitioner_id"

    def test_rejects_amt_practitioner_missing(
        self, admin_request_context, monkeypatch
    ):
        def fake_get(path, params=None):
            if path == "Practitioner/pr-abc":
                return _make_response(404)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 400
            assert "Practitioner resource not found" in response.get_json()["error"]

    def test_rejects_no_oscar_practitioner(
        self, admin_request_context, monkeypatch
    ):
        def fake_get(path, params=None):
            if path == "Practitioner/pr-abc":
                return _make_response(200, _amt_resource())
            if path == "Practitioner" and params.get("identifier"):
                return _make_response(200, {"resourceType": "Bundle", "entry": []})
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )
        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 404
            assert "Oscar Practitioner not found" in response.get_json()["error"]

    def test_success_adds_identifier_and_removes_from_orphan(
        self, admin_request_context, monkeypatch
    ):
        orphan = _orphan_resource("100001")
        search_bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": _amt_resource()},  # no Oscar id yet
                {"resource": orphan},
            ],
        }

        def fake_get(path, params=None):
            if path == "Practitioner/pr-abc":
                return _make_response(200, _amt_resource())
            if path == "Practitioner" and params.get("identifier"):
                return _make_response(200, search_bundle)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )

        puts = []

        def fake_put(path, resource):
            puts.append((path, resource))
            return _make_response(200)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_put", fake_put
        )

        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")

        assert status == 200
        assert response.get_json()["success"] is True
        assert response.get_json()["linked"] is True
        assert len(puts) == 2
        orphan_path, orphan_body = puts[0]
        assert orphan_path == "Practitioner/1003"
        assert not any(
            i.get("system") == OSCAR_PROVIDER_SYSTEM
            and i.get("value") == "100001"
            for i in orphan_body.get("identifier", [])
        )
        # Billing identifier must be preserved.
        assert any(
            i.get("system") == "http://hl7.org/fhir/sid/ca-bc-billing"
            for i in orphan_body.get("identifier", [])
        )
        amt_path, amt_body = puts[1]
        assert amt_path == "Practitioner/pr-abc"
        assert any(
            i.get("system") == OSCAR_PROVIDER_SYSTEM
            and i.get("value") == "100001"
            for i in amt_body.get("identifier", [])
        )

    def test_idempotent_already_linked(
        self, admin_request_context, monkeypatch
    ):
        search_bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": _amt_resource(with_oscar_id=True)}],
        }

        def fake_get(path, params=None):
            if path == "Practitioner/pr-abc":
                return _make_response(200, _amt_resource(with_oscar_id=True))
            if path == "Practitioner" and params.get("identifier"):
                return _make_response(200, search_bundle)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )

        puts = []

        def fake_put(path, resource):
            puts.append((path, resource))
            return _make_response(200)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_put", fake_put
        )

        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")

        assert status == 200
        assert response.get_json()["success"] is True
        assert response.get_json()["linked"] is False
        assert len(puts) == 0

    def test_502_when_remove_put_fails(
        self, admin_request_context, monkeypatch
    ):
        search_bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": _amt_resource()},
                {"resource": _orphan_resource("100001")},
            ],
        }

        def fake_get(path, params=None):
            if path == "Practitioner/pr-abc":
                return _make_response(200, _amt_resource())
            if path == "Practitioner" and params.get("identifier"):
                return _make_response(200, search_bundle)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )

        def fake_put(path, resource):
            return _make_response(500)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_put", fake_put
        )

        with Flask(__name__).test_request_context(
            method="POST", json={"oscar_provider_no": "100001"}
        ):
            g.user_role = "admin"
            response, status = link_oscar_provider_route.__wrapped__("user-123")
            assert status == 502


class TestOscarProviderCandidates:
    @pytest.fixture(autouse=True)
    def patch_user(self, monkeypatch, provider_user):
        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._get_user_by_id",
            lambda uid: provider_user if uid == provider_user.id else None,
        )

    def test_requires_admin(self, admin_request_context):
        with Flask(__name__).test_request_context(method="GET"):
            g.user_role = "provider"
            response, status = get_oscar_provider_candidates_route.__wrapped__("user-123")
            assert status == 403

    def test_returns_empty_for_missing_email(
        self, admin_request_context, monkeypatch, provider_user
    ):
        provider_user.email = ""
        with Flask(__name__).test_request_context(method="GET"):
            g.user_role = "admin"
            response, status = get_oscar_provider_candidates_route.__wrapped__("user-123")
            assert status == 200
            assert response.get_json()["candidates"] == []

    def test_returns_oscar_matches_only(
        self, admin_request_context, monkeypatch
    ):
        candidates_bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": _orphan_resource("100001")
                },
                {
                    "resource": {
                        "resourceType": "Practitioner",
                        "id": "1004",
                        "telecom": [{"system": "email", "value": "jones@example.com"}],
                    }
                },
            ],
        }

        def fake_get(path, params=None):
            if path == "Practitioner" and params.get("telecom"):
                return _make_response(200, candidates_bundle)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )

        with Flask(__name__).test_request_context(method="GET"):
            g.user_role = "admin"
            response, status = get_oscar_provider_candidates_route.__wrapped__("user-123")

        assert status == 200
        candidates = response.get_json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["practitioner_id"] == "1003"
        assert candidates[0]["oscar_provider_nos"] == ["100001"]

    def test_502_when_hapi_search_fails(
        self, admin_request_context, monkeypatch
    ):
        def fake_get(path, params=None):
            if path == "Practitioner" and params.get("telecom"):
                return _make_response(500)
            return _make_response(404)

        monkeypatch.setattr(
            "lib.routes.admin_provider_identity._fhir_get", fake_get
        )

        with Flask(__name__).test_request_context(method="GET"):
            g.user_role = "admin"
            response, status = get_oscar_provider_candidates_route.__wrapped__("user-123")
            assert status == 502
