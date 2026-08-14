"""
Unit tests for patient FHIR provisioning.
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

from lib.services.fhir_client import (
    AMT_DEMOGRAPHIC_SYSTEM,
    AMT_PATIENT_SOURCE,
    _build_patient_resource,
    _patient_id_from_response,
    ensure_patient,
)


def _make_response(status_code: int, json_data=None, headers=None) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
        resp.text = json.dumps(json_data)
    else:
        resp.json.return_value = None
        resp.text = ""
    return resp


class TestBuildPatientResource:
    def test_stamps_provider_created_source(self):
        resource = _build_patient_resource("1000")
        assert resource["meta"]["source"] == AMT_PATIENT_SOURCE

    def test_uses_amt_demographic_identifier(self):
        resource = _build_patient_resource("1000")
        assert resource["identifier"] == [
            {"system": AMT_DEMOGRAPHIC_SYSTEM, "value": "1000"}
        ]
        for ident in resource["identifier"]:
            assert "oscar" not in ident["system"]

    def test_maps_sex_to_fhir_gender(self):
        resource = _build_patient_resource("1000", sex="F")
        assert resource["gender"] == "female"

    def test_includes_name_and_telecom(self):
        resource = _build_patient_resource(
            "1000",
            first_name="Jane",
            last_name="Doe",
            phone="555-1234",
            email="jane@example.com",
            date_of_birth="1980-01-01",
        )
        assert resource["name"] == [{"family": "Doe", "given": ["Jane"]}]
        assert resource["telecom"] == [
            {"system": "phone", "value": "555-1234"},
            {"system": "email", "value": "jane@example.com"},
        ]
        assert resource["birthDate"] == "1980-01-01"


class TestEnsurePatient:
    @pytest.fixture(autouse=True)
    def patch_token(self, monkeypatch):
        monkeypatch.setattr(
            "lib.services.fhir_client._get_keycloak_token", lambda: "token"
        )

    def test_creates_patient_and_returns_id_from_location(self, monkeypatch):
        def fake_post(url, json=None, headers=None, timeout=None):
            assert headers.get("If-None-Exist").startswith("identifier=")
            assert AMT_DEMOGRAPHIC_SYSTEM in headers["If-None-Exist"]
            assert "|1000" in headers["If-None-Exist"]
            return _make_response(
                201,
                headers={"Location": "http://fake-hapi/fhir/Patient/123/_history/1"},
            )

        monkeypatch.setattr("lib.services.fhir_client.requests.post", fake_post)

        patient_id = ensure_patient("1000", first_name="Jane", last_name="Doe")
        assert patient_id == "123"

    def test_returns_existing_patient_from_200_response(self, monkeypatch):
        existing = {
            "resourceType": "Patient",
            "id": "456",
            "meta": {"source": AMT_PATIENT_SOURCE},
        }

        monkeypatch.setattr(
            "lib.services.fhir_client.requests.post",
            lambda *args, **kwargs: _make_response(200, existing),
        )

        # Second call with the same demographic_no is idempotent
        patient_id = ensure_patient("1000")
        assert patient_id == "456"

    def test_returns_none_on_hapi_failure(self, monkeypatch):
        monkeypatch.setattr(
            "lib.services.fhir_client.requests.post",
            lambda *args, **kwargs: _make_response(500, {"resourceType": "OperationOutcome"}),
        )

        assert ensure_patient("1000") is None


class TestPatientIdFromResponse:
    def test_extracts_from_bundle(self):
        resp = _make_response(200, {
            "resourceType": "Bundle",
            "entry": [{"resource": {"resourceType": "Patient", "id": "789"}}],
        })
        assert _patient_id_from_response(resp) == "789"
