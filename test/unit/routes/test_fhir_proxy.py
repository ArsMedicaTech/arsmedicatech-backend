"""
Unit tests for CareTeam-scoped provider authorization in the FHIR proxy.

These tests exercise the new helpers and the provider branch of
``_enforce_scope()`` without requiring a running HAPI server.
"""

import json
import sys
import time
import types
from unittest.mock import MagicMock, Mock, patch

# Provide a minimal fake settings module before any production code imports it.
# This avoids triggering Vault/Keycloak initialisation in the test environment.
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

# sentry_sdk is incompatible with Python 3.14 in this environment; mock it before
# importing the settings/logger chain that ``fhir_proxy.py`` pulls in.
if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

import pytest
from flask import Flask

from lib.models.user.user import User
from lib.routes.fhir_proxy import (
    CARE_TEAM_CACHE_TTL,
    MAX_PANEL_SIZE,
    _care_team_cache,
    _enforce_scope,
    _extract_patient_reference,
    _extract_resource_patient_id,
    _flush_care_team_cache,
    _forward_request,
    _get_active_care_team_count,
    _get_provider_panel,
    _is_on_care_team,
    _validate_bundle_entry,
)


@pytest.fixture
def app_context():
    """Provide a minimal Flask application context for tests touching ``g``."""
    app = Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def clear_care_team_cache():
    """Ensure each test starts with a clean membership cache."""
    _flush_care_team_cache()
    yield
    _flush_care_team_cache()


@pytest.fixture
def provider_user():
    return User(
        username="dr_jones",
        email="jones@example.com",
        role="provider",
        fhir_practitioner_id="pr-jones",
    )


@pytest.fixture
def patient_user():
    return User(
        username="patient_1007",
        email="p1007@example.com",
        role="patient",
        fhir_patient_id="1007",
    )


@pytest.fixture
def mock_requests_get():
    with patch("lib.routes.fhir_proxy.requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def mock_requests_request():
    with patch("lib.routes.fhir_proxy.requests.request") as mock_request:
        yield mock_request


def _mock_response(status_code, json_payload=None):
    resp = Mock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/fhir+json"}
    if json_payload is not None:
        resp.json.return_value = json_payload
    resp.content = json.dumps(json_payload or {}).encode("utf-8")
    return resp


class TestCareTeamMembershipCheck:
    """Tests for ``_is_on_care_team``."""

    def test_member_returns_true(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"total": 1})
        assert _is_on_care_team("pr-jones", "1007") is True

    def test_non_member_returns_false(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"total": 0})
        assert _is_on_care_team("pr-jones", "1007") is False

    def test_upstream_non_200_fails_closed(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(500, {"issue": ["boom"]})
        assert _is_on_care_team("pr-jones", "1007") is False

    def test_upstream_exception_fails_closed(self, mock_requests_get):
        mock_requests_get.side_effect = RuntimeError("timeout")
        assert _is_on_care_team("pr-jones", "1007") is False

    def test_caches_result_within_ttl(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"total": 1})
        assert _is_on_care_team("pr-jones", "1007") is True
        assert _is_on_care_team("pr-jones", "1007") is True
        assert mock_requests_get.call_count == 1

    def test_refetches_after_ttl(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"total": 1})
        _is_on_care_team("pr-jones", "1007")

        # Move past the TTL boundary.
        _care_team_cache[("pr-jones", "1007")] = (True, time.time() - 1)

        _is_on_care_team("pr-jones", "1007")
        assert mock_requests_get.call_count == 2

    def test_query_includes_summary_count(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"total": 1})
        _is_on_care_team("pr-jones", "1007")
        call_args = mock_requests_get.call_args
        params = call_args.kwargs["params"]
        assert params["patient"] == "1007"
        assert params["participant"] == "Practitioner/pr-jones"
        assert params["status"] == "active"
        assert params["_summary"] == "count"


class TestProviderPanel:
    """Tests for ``_get_provider_panel``."""

    def test_collects_subject_patient_ids(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(
            200,
            {
                "entry": [
                    {"resource": {"subject": {"reference": "Patient/1007"}}},
                    {"resource": {"subject": {"reference": "Patient/1008"}}},
                ]
            },
        )
        panel = _get_provider_panel("pr-jones")
        assert set(panel) == {"1007", "1008"}

    def test_empty_panel(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(200, {"entry": []})
        assert _get_provider_panel("pr-jones") == []

    def test_exceeds_max_panel_size(self, mock_requests_get):
        panel_entries = [
            {"resource": {"subject": {"reference": f"Patient/{i}"}}}
            for i in range(MAX_PANEL_SIZE + 1)
        ]
        mock_requests_get.return_value = _mock_response(200, {"entry": panel_entries})
        with pytest.raises(ValueError) as exc_info:
            _get_provider_panel("pr-jones")
        assert "exceeds" in str(exc_info.value).lower()
        assert str(MAX_PANEL_SIZE) in str(exc_info.value)

    def test_upstream_error_fails_closed(self, mock_requests_get):
        mock_requests_get.return_value = _mock_response(500)
        with pytest.raises(ValueError, match="Failed to load provider panel"):
            _get_provider_panel("pr-jones")


class TestExtractPatientReference:
    """Tests for ``_extract_patient_reference`` and ``_extract_resource_patient_id``."""

    @pytest.mark.parametrize(
        "body,expected",
        [
            ({"subject": {"reference": "Patient/1007"}}, "1007"),
            ({"patient": {"reference": "Patient/1007"}}, "1007"),
            ({"beneficiary": {"reference": "Patient/1007"}}, "1007"),
            ({"subject": "Patient/1007"}, "1007"),
            ({"subject": {"reference": "1007"}}, "1007"),
            ({"subject": {"reference": "http://example.com/Patient/1007"}}, "1007"),
            ({"other": "Patient/1007"}, None),
            ({}, None),
        ],
    )
    def test_extract_patient_reference(self, body, expected):
        assert _extract_patient_reference(body) == expected

    def test_extract_resource_patient_id_for_patient(self):
        assert _extract_resource_patient_id({"id": "1007"}, "Patient", "1007") == "1007"

    def test_extract_resource_patient_id_for_encounter(self):
        assert (
            _extract_resource_patient_id(
                {"subject": {"reference": "Patient/1007"}}, "Encounter", "abc"
            )
            == "1007"
        )


@pytest.mark.usefixtures("app_context")
class TestEnforceScopeProvider:
    """Tests for the provider branch of ``_enforce_scope``."""

    def test_null_practitioner_id_denied(self, provider_user):
        provider_user.fhir_practitioner_id = None
        params = {}
        with pytest.raises(ValueError, match="not linked to a Practitioner record"):
            _enforce_scope("Encounter", None, "GET", params, None, provider_user)

    def test_non_patient_data_type_allowed(self, provider_user):
        params = {}
        # Practitioner, Organization, Location etc. are not patient data.
        _enforce_scope("Practitioner", None, "GET", params, None, provider_user)
        assert params == {}

    def test_patient_search_no_panel_returns_empty_flag(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._get_provider_panel", lambda _prid: []
        )
        params = {}
        _enforce_scope("Patient", None, "GET", params, None, provider_user)
        from flask import g

        assert g.fhir_empty_panel is True

    def test_patient_search_injects_panel_ids(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._get_provider_panel", lambda _prid: ["1007", "1008"]
        )
        params = {}
        _enforce_scope("Patient", None, "GET", params, None, provider_user)
        assert params["_id"] == ["1007,1008"]

    def test_patient_read_by_id_sets_post_auth_flag(self, provider_user):
        params = {}
        _enforce_scope("Patient", "1007", "GET", params, None, provider_user)
        from flask import g

        assert g.fhir_post_auth_patient_check is True

    @pytest.mark.parametrize(
        "resource_type",
        ["Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "FamilyMemberHistory"],
    )
    def test_member_allowed_for_patient_scoped_search(self, resource_type, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        params = {"patient": ["1007"]}
        _enforce_scope(resource_type, None, "GET", params, None, provider_user)
        assert params["patient"] == ["1007"]

    @pytest.mark.parametrize(
        "resource_type",
        ["Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "FamilyMemberHistory"],
    )
    def test_non_member_denied_for_patient_scoped_search(self, resource_type, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        params = {"patient": ["1007"]}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope(resource_type, None, "GET", params, None, provider_user)

    @pytest.mark.parametrize(
        "resource_type",
        ["Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "FamilyMemberHistory"],
    )
    def test_patient_scoped_search_without_param_denied(self, resource_type, provider_user):
        params = {}
        with pytest.raises(ValueError, match="must be scoped to a specific patient"):
            _enforce_scope(resource_type, None, "GET", params, None, provider_user)

    def test_write_to_patient_scoped_type_member_allowed(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        body = {"subject": {"reference": "Patient/1007"}, "resourceType": "Encounter"}
        params = {}
        _enforce_scope("Encounter", None, "POST", params, body, provider_user)

    def test_write_to_patient_scoped_type_non_member_denied(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        body = {"subject": {"reference": "Patient/1007"}, "resourceType": "Encounter"}
        params = {}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope("Encounter", None, "POST", params, body, provider_user)

    def test_write_to_patient_scoped_type_without_patient_reference_denied(
        self, provider_user, monkeypatch
    ):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        body = {"status": "in-progress", "resourceType": "Encounter"}
        params = {}
        with pytest.raises(ValueError, match="must reference a patient"):
            _enforce_scope("Encounter", None, "POST", params, body, provider_user)

    def test_read_by_id_sets_post_auth_flag(self, provider_user):
        params = {}
        _enforce_scope("Encounter", "abc", "GET", params, None, provider_user)
        from flask import g

        assert g.fhir_post_auth_patient_check is True


@pytest.mark.usefixtures("app_context")
class TestEnforceScopeCareTeam:
    """Tests for provider CareTeam write/read rules (D3)."""

    def test_provider_not_on_team_cannot_create_care_team(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        body = {
            "resourceType": "CareTeam",
            "subject": {"reference": "Patient/1007"},
            "participant": [{"member": {"reference": "Practitioner/pr-jones"}}],
        }
        params = {}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope("CareTeam", None, "POST", params, body, provider_user)

    def test_provider_on_team_can_add_colleague(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        body = {
            "resourceType": "CareTeam",
            "id": "ct-1",
            "subject": {"reference": "Patient/1007"},
            "participant": [
                {"member": {"reference": "Practitioner/pr-jones"}},
                {"member": {"reference": "Practitioner/pr-smith"}},
            ],
        }
        params = {}
        _enforce_scope("CareTeam", "ct-1", "PUT", params, body, provider_user)

    def test_care_team_read_by_id_sets_post_auth_flag(self, provider_user):
        params = {}
        _enforce_scope("CareTeam", "ct-1", "GET", params, None, provider_user)
        from flask import g

        assert g.fhir_post_auth_patient_check is True

    def test_care_team_search_without_patient_denied(self, provider_user):
        params = {}
        with pytest.raises(ValueError, match="must be scoped to a patient"):
            _enforce_scope("CareTeam", None, "GET", params, None, provider_user)

    def test_care_team_search_non_member_denied(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        params = {"patient": ["1007"]}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope("CareTeam", None, "GET", params, None, provider_user)

    def test_care_team_bootstrap_allows_first_create(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._get_active_care_team_count", lambda _pid: 0
        )
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        body = {
            "resourceType": "CareTeam",
            "subject": {"reference": "Patient/1007"},
            "participant": [{"member": {"reference": "Practitioner/pr-jones"}}],
        }
        params = {}
        _enforce_scope("CareTeam", None, "POST", params, body, provider_user)

    def test_care_team_post_blocked_when_care_team_exists_and_not_member(
        self, provider_user, monkeypatch
    ):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._get_active_care_team_count", lambda _pid: 1
        )
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        body = {
            "resourceType": "CareTeam",
            "subject": {"reference": "Patient/1007"},
            "participant": [{"member": {"reference": "Practitioner/pr-jones"}}],
        }
        params = {}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope("CareTeam", None, "POST", params, body, provider_user)

    def test_care_team_count_query_failure_fails_closed(
        self, provider_user, monkeypatch, mock_requests_get
    ):
        mock_requests_get.side_effect = RuntimeError("boom")
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        body = {
            "resourceType": "CareTeam",
            "subject": {"reference": "Patient/1007"},
            "participant": [{"member": {"reference": "Practitioner/pr-jones"}}],
        }
        params = {}
        with pytest.raises(ValueError, match="not a participant"):
            _enforce_scope("CareTeam", None, "POST", params, body, provider_user)


@pytest.mark.usefixtures("app_context")
class TestForwardRequest:
    """Tests for post-fetch authorization and cache flush in ``_forward_request``."""

    def test_post_fetch_denies_non_member(self, provider_user, mock_requests_request, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/fhir+json"}
        mock_response.json.return_value = {
            "resourceType": "Encounter",
            "id": "abc",
            "subject": {"reference": "Patient/1007"},
        }
        mock_response.content = json.dumps(mock_response.json.return_value).encode("utf-8")
        mock_requests_request.return_value = mock_response

        with patch("lib.routes.fhir_proxy.g") as mock_g:
            mock_g.fhir_post_auth_patient_check = True
            response, status = _forward_request(
                "GET",
                "http://hapi/Encounter/abc",
                {},
                b"",
                {},
                provider_user,
                "Encounter",
                "abc",
                {},
            )
        assert status == 403
        assert "not a participant" in response.get_json()["error"]

    def test_post_fetch_allows_member(self, provider_user, mock_requests_request, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/fhir+json"}
        mock_response.json.return_value = {
            "resourceType": "Encounter",
            "id": "abc",
            "subject": {"reference": "Patient/1007"},
        }
        mock_response.content = json.dumps(mock_response.json.return_value).encode("utf-8")
        mock_requests_request.return_value = mock_response

        with patch("lib.routes.fhir_proxy.g") as mock_g:
            mock_g.fhir_post_auth_patient_check = True
            response = _forward_request(
                "GET",
                "http://hapi/Encounter/abc",
                {},
                b"",
                {},
                provider_user,
                "Encounter",
                "abc",
                {},
            )
        assert response.status_code == 200

    def test_cache_flushed_on_careteam_post(self, provider_user, mock_requests_request):
        _care_team_cache[("pr-jones", "1007")] = (True, time.time() + CARE_TEAM_CACHE_TTL)
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"Location": "CareTeam/ct-1"}
        mock_response.content = b""
        mock_requests_request.return_value = mock_response

        with patch("lib.routes.fhir_proxy.g") as mock_g:
            mock_g.fhir_post_auth_patient_check = False
            _forward_request(
                "POST",
                "http://hapi/CareTeam",
                {},
                b'{"resourceType":"CareTeam"}',
                {},
                provider_user,
                "CareTeam",
                None,
                {},
            )
        assert ("pr-jones", "1007") not in _care_team_cache

    def test_cache_not_flushed_on_other_resource(self, provider_user, mock_requests_request):
        _care_team_cache[("pr-jones", "1007")] = (True, time.time() + CARE_TEAM_CACHE_TTL)
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_response.content = b""
        mock_requests_request.return_value = mock_response

        with patch("lib.routes.fhir_proxy.g") as mock_g:
            mock_g.fhir_post_auth_patient_check = False
            _forward_request(
                "POST",
                "http://hapi/Encounter",
                {},
                b'{"resourceType":"Encounter"}',
                {},
                provider_user,
                "Encounter",
                None,
                {},
            )
        assert ("pr-jones", "1007") in _care_team_cache


@pytest.mark.usefixtures("app_context")
class TestBundleAuthorization:
    """Tests for transaction Bundle entry authorization."""

    def test_bundle_entry_non_panel_patient_denied(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        entry = {
            "request": {"method": "GET", "url": "Encounter?patient=9999"},
        }
        with pytest.raises(ValueError, match="not a participant"):
            _validate_bundle_entry(entry, provider_user)

    def test_bundle_entry_member_allowed(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: True
        )
        entry = {
            "request": {"method": "GET", "url": "Encounter?patient=1007"},
        }
        _validate_bundle_entry(entry, provider_user)

    def test_bundle_entry_provider_adds_self_to_team_denied(self, provider_user, monkeypatch):
        monkeypatch.setattr(
            "lib.routes.fhir_proxy._is_on_care_team", lambda _prid, _pid: False
        )
        entry = {
            "request": {
                "method": "POST",
                "url": "CareTeam",
            },
            "resource": {
                "resourceType": "CareTeam",
                "subject": {"reference": "Patient/1007"},
                "participant": [{"member": {"reference": "Practitioner/pr-jones"}}],
            },
        }
        with pytest.raises(ValueError, match="not a participant"):
            _validate_bundle_entry(entry, provider_user)
