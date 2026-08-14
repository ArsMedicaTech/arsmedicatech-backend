"""
vault_loader.py
---------------
Pulls secrets from Vault and injects them into os.environ so that
settings.py (and anything else reading os.environ) works without
any modification.

Designed to be called at the very top of your application entrypoint,
before any other imports that read os.environ.

Authentication inside Kubernetes uses the pod's ServiceAccount JWT
(Kubernetes auth method) — no token or credential needs to be
hard-coded or mounted manually.

Outside Kubernetes (local dev), falls back to VAULT_TOKEN env var
so developers can point at a local Vault dev server.

Usage — in your Flask entrypoint (e.g. app.py or wsgi.py):

    from vault_loader import load_vault_secrets

    load_vault_secrets()          # must be first

    from settings import *        # now sees fully populated os.environ
    from flask import Flask
    ...
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import hvac
from hvac.exceptions import Forbidden, InvalidPath

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — override via env vars if needed
# ---------------------------------------------------------------------------

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault.vault.svc.cluster.local:8200")
VAULT_KV_MOUNT = os.environ.get("VAULT_KV_MOUNT", "secret")
VAULT_AUTH_METHOD = os.environ.get(
    "VAULT_AUTH_METHOD", "token"
)  # "auto" | "token" | "kubernetes"
VAULT_K8S_ROLE = os.environ.get("VAULT_K8S_ROLE", "")  # required for kubernetes auth
VAULT_K8S_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

# Service name drives which Vault paths are read:
#   KV secrets  → secret/data/<SERVICE_NAME>/secrets
#   Dynamic DB  → database/creds/<VAULT_DB_ROLE>
SERVICE_NAME = os.environ.get("SERVICE_NAME", "amt-oss-backend")  # e.g. "my-api"
VAULT_DB_ROLES = os.environ.get("VAULT_DB_ROLES", "")  # comma-separated role names


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _auth_token(client: hvac.Client) -> hvac.Client:
    """Authenticate using a static VAULT_TOKEN (local dev / CI)."""
    token = os.environ.get("VAULT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "VAULT_AUTH_METHOD=token but VAULT_TOKEN is not set. "
            "Set it in your environment or switch to kubernetes auth."
        )
    client.token = token
    if not client.is_authenticated():
        raise RuntimeError("Vault token authentication failed — check VAULT_TOKEN.")
    logger.info("Vault: authenticated via static token")
    return client


def _auth_kubernetes(client: hvac.Client, role: str) -> hvac.Client:
    """
    Authenticate using the pod's ServiceAccount JWT.
    Vault must have the kubernetes auth method enabled and the role configured.
    (The provisioning script in env_provision.py sets this up.)
    """
    if not role:
        raise RuntimeError(
            "VAULT_AUTH_METHOD=kubernetes but VAULT_K8S_ROLE is not set. "
            "Set it to the Vault role bound to this pod's ServiceAccount."
        )

    jwt_path = Path(VAULT_K8S_JWT_PATH)
    if not jwt_path.exists():
        raise RuntimeError(
            f"Kubernetes ServiceAccount JWT not found at {VAULT_K8S_JWT_PATH}. "
            "Are you running inside a Kubernetes pod?"
        )

    jwt = jwt_path.read_text().strip()
    response = client.auth.kubernetes.login(role=role, jwt=jwt)
    client.token = response["auth"]["client_token"]

    if not client.is_authenticated():
        raise RuntimeError(
            f"Vault Kubernetes auth failed for role '{role}'. "
            "Check that the role exists and binds this pod's ServiceAccount."
        )

    logger.info("Vault: authenticated via Kubernetes ServiceAccount (role=%s)", role)
    return client


def _auto_auth(client: hvac.Client, role: str) -> hvac.Client:
    """
    Try Kubernetes auth first (inside a pod), fall back to token auth (local dev).
    This lets the same code run in both environments without any changes.
    """
    if Path(VAULT_K8S_JWT_PATH).exists() and role:
        try:
            return _auth_kubernetes(client, role)
        except Exception as exc:
            logger.warning(
                "Kubernetes auth failed (%s), falling back to token auth", exc
            )

    return _auth_token(client)


def _connect(retries: int = 5, delay: float = 2.0) -> hvac.Client:
    """
    Create and authenticate a Vault client.
    Retries on connection failure — useful during pod startup when
    Vault may not yet be reachable.
    """
    client = hvac.Client(url=VAULT_ADDR)

    method = VAULT_AUTH_METHOD.lower()

    for attempt in range(1, retries + 1):
        try:
            client.sys.read_health_status(
                method="GET"
            )  # lightweight connectivity check
            break
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Could not reach Vault at {VAULT_ADDR} after {retries} attempts: {exc}"
                ) from exc
            logger.warning(
                "Vault not reachable (attempt %d/%d): %s — retrying in %.0fs",
                attempt,
                retries,
                exc,
                delay,
            )
            time.sleep(delay)

    if method == "token":
        return _auth_token(client)
    elif method == "kubernetes":
        return _auth_kubernetes(client, VAULT_K8S_ROLE)
    else:  # "auto"
        return _auto_auth(client, VAULT_K8S_ROLE)


# ---------------------------------------------------------------------------
# Secret fetchers
# ---------------------------------------------------------------------------


def _fetch_kv_secrets(client: hvac.Client, service: str) -> dict[str, str]:
    """
    Read all key-value pairs from secret/<service>/secrets.
    Returns an empty dict if the path doesn't exist (non-fatal).
    """
    path = f"{service}/secrets"
    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=path,
            mount_point=VAULT_KV_MOUNT,
            raise_on_deleted_version=True,
        )
        data = response["data"]["data"]
        logger.info(
            "Vault KV: loaded %d secret(s) from %s/%s",
            len(data),
            VAULT_KV_MOUNT,
            path,
        )
        return {str(k): str(v) for k, v in data.items()}

    except InvalidPath:
        logger.warning(
            "Vault KV: path '%s/%s' not found — skipping", VAULT_KV_MOUNT, path
        )
        return {}
    except Forbidden:
        raise RuntimeError(
            f"Vault KV: permission denied reading '{VAULT_KV_MOUNT}/{path}'. "
            "Check the policy attached to this pod's Vault role."
        )


def _fetch_dynamic_db_creds(client: hvac.Client, role: str) -> dict[str, str]:
    """
    Request a fresh set of database credentials from Vault's database
    secrets engine for the given role.

    Vault generates a short-lived username/password pair and returns them.
    The lease is tied to this pod's Vault token and expires automatically.

    Naming convention: the env var names are derived from the role name.
    e.g. role "my-api-db-role" → MY_API_DB_ROLE_USERNAME / MY_API_DB_ROLE_PASSWORD
    """
    try:
        response = client.secrets.database.generate_credentials(name=role)
        creds = response["data"]
        username = creds["username"]
        password = creds["password"]
        lease_id = response.get("lease_id", "")
        ttl = response.get("lease_duration", "unknown")

        logger.info(
            "Vault DB: generated credentials for role '%s' (lease=%s, ttl=%ss)",
            role,
            lease_id,
            ttl,
        )

        # Derive env var names from the role name:
        # "my-api-db-role" → MY_API_DB_ROLE
        env_prefix = role.upper().replace("-", "_")
        return {
            f"{env_prefix}_USERNAME": username,
            f"{env_prefix}_PASSWORD": password,
        }

    except InvalidPath:
        raise RuntimeError(
            f"Vault DB: role '{role}' not found. "
            "Run env_provision.py to configure the database secrets engine."
        )
    except Forbidden:
        raise RuntimeError(
            f"Vault DB: permission denied generating credentials for role '{role}'. "
            "Check the policy attached to this pod's Vault role."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_vault_secrets(
    service_name: Optional[str] = None,
    db_roles: Optional[list[str]] = None,
    overwrite: bool = False,
) -> dict[str, str]:
    """
    Pull secrets from Vault and inject them into os.environ.

    Args:
        service_name:  Vault path prefix. Defaults to SERVICE_NAME env var.
        db_roles:      List of Vault DB role names to generate credentials for.
                       Defaults to VAULT_DB_ROLES env var (comma-separated).
        overwrite:     If False (default), existing os.environ values are not
                       overwritten — letting Kubernetes-injected values take
                       precedence if they exist.

    Returns:
        Dict of all values that were injected (for logging/debugging).
    """
    service = service_name or SERVICE_NAME
    if not service:
        raise RuntimeError(
            "SERVICE_NAME is not set. Pass service_name= or set the SERVICE_NAME env var."
        )

    roles: list[str] = db_roles or [
        r.strip() for r in VAULT_DB_ROLES.split(",") if r.strip()
    ]

    logger.info("vault_loader: starting  service=%s  vault=%s", service, VAULT_ADDR)

    client = _connect()
    injected = {}

    # ── Scenario 2: KV secrets ───────────────────────────────────────────────
    kv_values = _fetch_kv_secrets(client, service)
    for key, value in kv_values.items():
        if key not in os.environ or overwrite:
            os.environ[key] = value
            injected[key] = value
        else:
            logger.debug("Skipping '%s' — already set in environment", key)

    # ── Scenario 3: Dynamic database credentials ─────────────────────────────
    for role in roles:
        db_creds = _fetch_dynamic_db_creds(client, role)
        for key, value in db_creds.items():
            if key not in os.environ or overwrite:
                os.environ[key] = value
                injected[key] = value
            else:
                logger.debug("Skipping '%s' — already set in environment", key)

    logger.info(
        "vault_loader: done — injected %d value(s) into os.environ", len(injected)
    )
    return injected
