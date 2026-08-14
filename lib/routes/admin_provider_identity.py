"""
Admin endpoints for linking an AMT provider account to an Oscar provider identity.

This closes the identity gap between AMT-native Practitioners (id ``pr-{external_id}``) and
Oscar-synced Practitioners (identified by ``oscar-provider|<provider_no>``). After linking,
fhir-sync's existing conditional reference resolves to the AMT Practitioner, so
``_is_on_care_team()`` can match the provider.
"""

from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Response, g, jsonify, request

from lib.models.user.user import User
from lib.services.auth_decorators import require_auth
from lib.services.fhir_client import _fhir_headers
from lib.services.user_service import UserService
from settings import FHIR_BASE_URL, logger

OSCAR_PROVIDER_SYSTEM = "oscar-provider"
_ADMIN_ROLES = {"admin", "superadmin", "administrator"}


def _admin_user_id() -> Optional[str]:
    """Best-effort id of the admin performing the action."""
    session = getattr(g, "user_session", None)
    if session is not None:
        return str(session.user_id)
    return getattr(g, "user_id", None)


def _require_admin() -> Optional[Tuple[Response, int]]:
    """Return a 403 response if the current request is not from an admin."""
    if getattr(g, "user_role", None) not in _ADMIN_ROLES:
        return jsonify({"error": "Admin role required"}), 403
    return None


def _get_user_by_id(user_id: str) -> Optional[User]:
    """Load a user by SurrealDB id."""
    service = UserService()
    service.connect()
    try:
        return service.get_user_by_id(user_id)
    finally:
        service.close()


def _fhir_url(path: str) -> str:
    return f"{FHIR_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _fhir_get(path: str, params: Optional[Dict[str, str]] = None) -> requests.Response:
    return requests.get(
        _fhir_url(path), params=params or {}, headers=_fhir_headers(), timeout=10
    )


def _fhir_put(path: str, resource: Dict[str, Any]) -> requests.Response:
    return requests.put(
        _fhir_url(path), json=resource, headers=_fhir_headers(), timeout=10
    )


def _search_practitioner_by_identifier(
    system: str, value: str
) -> Optional[Dict[str, Any]]:
    """Search HAPI for Practitioners carrying a given identifier."""
    resp = _fhir_get("Practitioner", params={"identifier": f"{system}|{value}"})
    if resp.status_code != 200:
        logger.warning(
            f"Practitioner identifier search failed: status={resp.status_code} body={resp.text[:500]}"
        )
        return None
    return resp.json()


def _get_practitioner(resource_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single Practitioner resource by id."""
    resp = _fhir_get(f"Practitioner/{resource_id}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning(
            f"Practitioner read failed for {resource_id}: status={resp.status_code} body={resp.text[:500]}"
        )
        return None
    return resp.json()


def _has_identifier(
    resource: Dict[str, Any], system: str, value: Optional[str] = None
) -> bool:
    """Check whether a Practitioner resource carries an identifier."""
    for ident in resource.get("identifier", []):
        if ident.get("system") != system:
            continue
        if value is None or ident.get("value") == value:
            return True
    return False


def _add_identifier(
    resource: Dict[str, Any], system: str, value: str
) -> bool:
    """Append an identifier if not already present; return True if changed."""
    if _has_identifier(resource, system, value):
        return False
    resource.setdefault("identifier", []).append({"system": system, "value": value})
    return True


def _remove_identifier(
    resource: Dict[str, Any], system: str, value: str
) -> bool:
    """Remove all identifiers matching system+value; return True if changed."""
    original = resource.get("identifier", [])
    filtered = [
        ident
        for ident in original
        if not (ident.get("system") == system and ident.get("value") == value)
    ]
    if len(filtered) == len(original):
        return False
    resource["identifier"] = filtered
    return True


@require_auth
def link_oscar_provider_route(user_id: str) -> Tuple[Response, int]:
    """
    POST handler for ``/api/admin/providers/<user_id>/link-oscar-provider``.

    Adds the Oscar ``provider_no`` identifier to the AMT provider's Practitioner resource and
    removes the same identifier from any other Practitioner that carries it, so fhir-sync's
    conditional reference has an unambiguous resolution target.
    """
    denied = _require_admin()
    if denied is not None:
        return denied

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    body = request.get_json(silent=True) or {}
    oscar_provider_no = body.get("oscar_provider_no")
    if not oscar_provider_no or not isinstance(oscar_provider_no, str):
        return jsonify({"error": "oscar_provider_no is required"}), 400

    user = _get_user_by_id(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    if user.role != "provider":
        return jsonify({"error": "User must be a provider"}), 400
    if not user.fhir_practitioner_id:
        return jsonify({"error": "Provider has no fhir_practitioner_id"}), 400

    amt_resource = _get_practitioner(user.fhir_practitioner_id)
    if amt_resource is None:
        return (
            jsonify({"error": "Provider Practitioner resource not found in FHIR"}),
            400,
        )

    bundle = _search_practitioner_by_identifier(
        OSCAR_PROVIDER_SYSTEM, oscar_provider_no
    )
    if bundle is None:
        return jsonify({"error": "Failed to query Practitioner identifier"}), 502

    matched = [
        entry.get("resource", {})
        for entry in bundle.get("entry", [])
        if entry.get("resource")
    ]
    if not matched:
        return (
            jsonify({"error": "Oscar Practitioner not found for provider_no"}),
            404,
        )

    changed = False
    for resource in matched:
        if resource.get("id") == user.fhir_practitioner_id:
            continue
        if _remove_identifier(resource, OSCAR_PROVIDER_SYSTEM, oscar_provider_no):
            resp = _fhir_put(f"Practitioner/{resource['id']}", resource)
            if resp.status_code not in (200, 201):
                logger.warning(
                    f"Failed to remove Oscar identifier from Practitioner/{resource.get('id')}: "
                    f"status={resp.status_code} body={resp.text[:500]}"
                )
                return (
                    jsonify(
                        {"error": "Failed to remove Oscar identifier from existing Practitioner"}
                    ),
                    502,
                )
            changed = True

    if _add_identifier(amt_resource, OSCAR_PROVIDER_SYSTEM, oscar_provider_no):
        resp = _fhir_put(
            f"Practitioner/{user.fhir_practitioner_id}", amt_resource
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                f"Failed to add Oscar identifier to Practitioner/{user.fhir_practitioner_id}: "
                f"status={resp.status_code} body={resp.text[:500]}"
            )
            return (
                jsonify(
                    {"error": "Failed to add Oscar identifier to provider Practitioner"}
                ),
                502,
            )
        changed = True

    logger.info(
        f"Linked Oscar provider_no={oscar_provider_no} to user={user_id} "
        f"practitioner={user.fhir_practitioner_id} by admin={_admin_user_id()}"
    )
    return jsonify({"success": True, "linked": changed}), 200


@require_auth
def get_oscar_provider_candidates_route(user_id: str) -> Tuple[Response, int]:
    """
    GET handler for ``/api/admin/providers/<user_id>/oscar-candidates``.

    Returns Oscar-synced Practitioner resources whose email telecom matches the AMT user's
    email. The match is only a suggestion; the admin must explicitly confirm the link.
    """
    denied = _require_admin()
    if denied is not None:
        return denied

    user = _get_user_by_id(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    if user.role != "provider":
        return jsonify({"error": "User must be a provider"}), 400

    if not user.email:
        return jsonify({"candidates": []}), 200

    resp = _fhir_get("Practitioner", params={"telecom": f"email|{user.email}"})
    if resp.status_code != 200:
        logger.warning(
            f"Practitioner telecom search failed: status={resp.status_code} body={resp.text[:500]}"
        )
        return jsonify({"error": "Failed to query Practitioner candidates"}), 502

    bundle = resp.json()
    candidates: List[Dict[str, Any]] = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if not _has_identifier(resource, OSCAR_PROVIDER_SYSTEM):
            continue
        oscar_values = [
            ident.get("value")
            for ident in resource.get("identifier", [])
            if ident.get("system") == OSCAR_PROVIDER_SYSTEM
        ]
        candidates.append(
            {
                "practitioner_id": resource.get("id"),
                "name": resource.get("name"),
                "identifiers": resource.get("identifier"),
                "telecom": resource.get("telecom"),
                "oscar_provider_nos": oscar_values,
            }
        )

    return jsonify({"candidates": candidates}), 200
