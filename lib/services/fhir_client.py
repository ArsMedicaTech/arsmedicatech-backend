"""
Minimal FHIR client for backend-to-HAPI interactions.

Acquires an access token from the configured Keycloak realm using the
backend's client credentials, then uses that token to talk to the HAPI FHIR
server. This allows the backend to create/update Practitioner resources on
behalf of newly registered users without requiring a user session token.
"""

import time
from typing import Any, Dict, Optional

import requests
from settings import (
    FHIR_BASE_URL,
    KEYCLOAK_BASE_URL,
    KEYCLOAK_CLIENT_ID,
    KEYCLOAK_CLIENT_SECRET,
    KEYCLOAK_REALM,
    logger,
)


# Simple in-memory cache for the backend service token.
_keycloak_token_cache: Dict[str, Any] = {}


def _get_keycloak_token() -> Optional[str]:
    """
    Fetch (or return a cached) Keycloak access token for the backend client.

    :return: A bearer access token, or None if Keycloak is not configured.
    """
    if not KEYCLOAK_CLIENT_ID or not KEYCLOAK_CLIENT_SECRET:
        logger.debug("Keycloak client credentials not configured; skipping service token")
        return None

    now = time.time()
    cached = _keycloak_token_cache.get("token")
    expires_at = _keycloak_token_cache.get("expires_at", 0)
    if cached and now < expires_at - 30:  # 30-second buffer
        return str(cached)

    token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    try:
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
            },
            timeout=10,
        )
        if response.status_code not in (200, 201):
            logger.error(
                f"Failed to fetch Keycloak service token: status={response.status_code} body={response.text}"
            )
            return None

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 300)
        if not access_token:
            logger.error("Keycloak token response missing access_token")
            return None

        _keycloak_token_cache["token"] = access_token
        _keycloak_token_cache["expires_at"] = now + int(expires_in)
        logger.info("Fetched new Keycloak service token for HAPI FHIR")
        return str(access_token)
    except Exception as e:
        logger.error(f"Exception fetching Keycloak service token: {e}")
        return None


def _fhir_headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }
    token = _get_keycloak_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fhir_url(resource_type: str, resource_id: str) -> str:
    return f"{FHIR_BASE_URL}/{resource_type}/{resource_id}"


def _put_resource(
    resource_type: str, resource_id: str, resource: Dict[str, Any]
) -> Optional[requests.Response]:
    url = _fhir_url(resource_type, resource_id)
    headers = _fhir_headers()
    logger.debug(f"PUT {url} headers={list(headers.keys())}")
    response = requests.put(url, json=resource, headers=headers, timeout=10)
    logger.debug(
        f"PUT {url} status={response.status_code} body={response.text[:500]}"
    )
    if response.status_code in (200, 201):
        return response
    return None


def _post_resource(
    resource_type: str, resource: Dict[str, Any]
) -> Optional[requests.Response]:
    url = f"{FHIR_BASE_URL}/{resource_type}"
    headers = _fhir_headers()
    logger.debug(f"POST {url} headers={list(headers.keys())}")
    response = requests.post(url, json=resource, headers=headers, timeout=10)
    logger.debug(
        f"POST {url} status={response.status_code} body={response.text[:500]}"
    )
    if response.status_code in (200, 201):
        return response
    return None


def _build_practitioner_resource(
    practitioner_id: str,
    first_name: Optional[str],
    last_name: Optional[str],
    email: Optional[str],
) -> Dict[str, Any]:
    resource: Dict[str, Any] = {
        "resourceType": "Practitioner",
        "id": practitioner_id,
        "active": True,
        "name": [],
    }

    name: Dict[str, Any] = {}
    if last_name:
        name["family"] = last_name
    if first_name:
        name["given"] = [first_name]
    if name:
        resource["name"].append(name)

    if email:
        resource["telecom"] = [
            {
                "system": "email",
                "value": email,
                "use": "work",
            }
        ]

    return resource


def ensure_practitioner(
    practitioner_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[str]:
    """
    Ensure a Practitioner resource exists in the HAPI FHIR server.

    First attempts a PUT (create/update by ID). If the server rejects it,
    falls back to POST.

    :param practitioner_id: The FHIR Practitioner ID to ensure.
    :param first_name: The practitioner's first name.
    :param last_name: The practitioner's last name.
    :param email: The practitioner's email.
    :return: The server-assigned or provided Practitioner ID, or None on failure.
    """
    resource = _build_practitioner_resource(
        practitioner_id, first_name, last_name, email
    )

    try:
        response = _put_resource("Practitioner", practitioner_id, resource)
        if response:
            logger.info(f"Ensured Practitioner/{practitioner_id} in HAPI FHIR")
            return practitioner_id

        # PUT failed; try POST as fallback
        response = _post_resource("Practitioner", resource)
        if response and response.status_code in (200, 201):
            location = response.headers.get("Location")
            logger.info(
                f"Created Practitioner/{practitioner_id} via POST in HAPI FHIR"
            )
            return location.split("/")[-1] if location else practitioner_id

        logger.error(
            f"Failed to ensure Practitioner/{practitioner_id} in HAPI FHIR: "
            f"status={response.status_code if response else 'None'} "
            f"body={response.text if response else 'None'}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Exception ensuring Practitioner/{practitioner_id} in HAPI FHIR: {e}"
        )
        return None
