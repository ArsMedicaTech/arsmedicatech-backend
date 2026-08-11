""""""

import os
from os.path import dirname, join

from dotenv import load_dotenv

from lib.logger import Logger, SentryLogger

logger: Logger = Logger()


# import logging
# logging.basicConfig(level=logging.INFO)

# ── 1. Pull secrets into os.environ FIRST ────────────────────────────────────
from vault_loader import load_vault_secrets

load_vault_secrets()  # reads SERVICE_NAME + VAULT_DB_ROLES from env

dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)


SURREALDB_NAMESPACE = os.environ.get("SURREALDB_NAMESPACE")
SURREALDB_DATABASE = os.environ.get("SURREALDB_DATABASE")
SURREALDB_USER = os.environ.get("SURREALDB_USER")
SURREALDB_PASS = os.environ.get("SURREALDB_PASS")

SURREALDB_PROTOCOL = os.environ.get("SURREALDB_PROTOCOL", "ws")
SURREALDB_HOST = os.environ.get("SURREALDB_HOST", "localhost")
SURREALDB_PORT = os.environ.get("SURREALDB_PORT", 8700)

SURREALDB_URL = f"{SURREALDB_PROTOCOL}://{SURREALDB_HOST}:{SURREALDB_PORT}"

SURREALDB_ICD_DB = os.environ.get("SURREALDB_ICD_DB", "diagnosis")

print("SUREALDB_NAMESPACE:", SURREALDB_NAMESPACE)
print("SURREALDB_DATABASE:", SURREALDB_DATABASE)
print("SURREALDB_URL:", SURREALDB_URL)
print("SURREALDB_USER:", SURREALDB_USER)
print("SURREALDB_PASS:", SURREALDB_PASS)

# Security
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError(
        "ENCRYPTION_KEY must be set in settings.py or environment variable"
    )

print("ENCRYPTION_KEY:", "SET" if ENCRYPTION_KEY else "NOT SET")

PORT = os.environ.get("PORT", 5000)
DEBUG = True if os.environ.get("DEBUG", "true").lower() in ("true", "1", "t") else False
HOST = os.environ.get("HOST", "0.0.0.0")

print("PORT:", PORT)
print("DEBUG:", DEBUG)
print("HOST:", HOST)

NCBI_API_KEY = os.environ.get("NCBI_API_KEY")

MIGRATION_OPENAI_API_KEY = os.environ.get(
    "MIGRATION_OPENAI_API_KEY", "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
)

FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "super-secret-key")

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:3123/api")

FHIR_BASE_URL = os.environ.get("FHIR_BASE_URL", "https://fhir.synapticl.com/fhir")

FHIR_GATEWAY_URL = os.environ.get(
    "FHIR_GATEWAY_URL",
    "http://fhir-gateway.arsmedicatech-synapticl.svc.cluster.local:8080/fhir",
)

# MCP_URL = "http://localhost:9000/mcp"
MCP_URL = os.environ.get("MCP_URL", "http://mcp-server/mcp/")

TEST_OPTIMAL_KEY = os.environ.get(
    "OPTIMAL_KEY", "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
)
OPTIMAL_URL = os.environ.get(
    "OPTIMAL_URL", "https://optimal.apphosting.services/optimize"
)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

NOTIFICATIONS_CHANNEL = 0
UPLOADS_CHANNEL = 1

SENTRY_DSN = os.environ.get("SENTRY_DSN", None)
if not SENTRY_DSN:
    logger.error("SENTRY_DSN is not set. Sentry will not be initialized.")
    raise ValueError("SENTRY_DSN must be set in settings.py or environment variable")

SentryLogger.init(SENTRY_DSN)
sentry_logger: SentryLogger = SentryLogger()
logger._sentry = sentry_logger

DEMO_ADMIN_USERNAME = os.environ.get("DEMO_ADMIN_USERNAME", "admin")
DEMO_ADMIN_PASSWORD = os.environ.get("DEMO_ADMIN_PASSWORD", "admin")

BUCKET_NAME = os.environ.get("S3_BUCKET", "my-bucket")

S3_AWS_ACCESS_KEY_ID = os.environ.get("S3_AWS_ACCESS_KEY_ID", "your-access-key-id")
S3_AWS_SECRET_ACCESS_KEY = os.environ.get(
    "S3_SECRET_ACCESS_KEY", "your-secret-access-key"
)

TEXTRACT_AWS_ACCESS_KEY_ID = os.environ.get(
    "TEXTRACT_AWS_ACCESS_KEY_ID", "your-access-key-id"
)
TEXTRACT_AWS_SECRET_ACCESS_KEY = os.environ.get(
    "TEXTRACT_AWS_SECRET_ACCESS_KEY", "your-secret-access-key"
)

UMLS_API_KEY = os.environ.get("UMLS_API_KEY", "your-umls-api-key")

ICD_AUTOCODER_URL = os.environ.get("ICD_AUTOCODER_URL", "")
ICD_AUTOCODER_TIMEOUT = int(os.environ.get("ICD_AUTOCODER_TIMEOUT", 10))
ICD_AUTOCODER_RATE_LIMIT = int(os.environ.get("ICD_AUTOCODER_RATE_LIMIT", 60))
ICD_AUTOCODER_RATE_WINDOW = int(os.environ.get("ICD_AUTOCODER_RATE_WINDOW", 60))
ICD_AUTOCODER_FEEDBACK_TABLE = os.environ.get("ICD_AUTOCODER_FEEDBACK_TABLE", "icd_feedback")


# AWS Cognito Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "your-domain")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "your-user-pool-id")
CLIENT_ID = os.environ.get("USER_POOL_CLIENT_ID", "your-app-client-id")
CLIENT_SECRET = os.environ.get("USER_POOL_CLIENT_SECRET", "your-app-client-secret")

# LoginRadius OIDC Configuration
LOGINRADIUS_SITE_URL = os.environ.get(
    "LOGINRADIUS_SITE_URL", "https://your-site-url.hub.loginradius.com"
)
LOGINRADIUS_OIDC_APP_NAME = os.environ.get(
    "LOGINRADIUS_OIDC_APP_NAME", "your-oidc-app-name"
)
LOGINRADIUS_CLIENT_ID = os.environ.get("LOGINRADIUS_CLIENT_ID", "your-client-id")
LOGINRADIUS_CLIENT_SECRET = os.environ.get(
    "LOGINRADIUS_CLIENT_SECRET", "your-client-secret"
)


REDIRECT_URI = (
    f"http://localhost:{PORT}/api/auth/callback"
    if DEBUG
    else "https://demo.arsmedicatech.com/api/auth/callback"
)
COGNITO_LOGIN_URL = f"https://{COGNITO_DOMAIN}/oauth2/authorize?client_id={CLIENT_ID}&response_type=code&scope=openid+email+profile&redirect_uri={REDIRECT_URI}&identity_provider=Google"

LOGOUT_URI = f"http://localhost:{PORT}/" if DEBUG else "https://demo.arsmedicatech.com/"


REACT_PORT = os.environ.get("REACT_PORT", 3000)
APP_URL = (
    f"http://localhost:{REACT_PORT}/" if DEBUG else "https://demo.arsmedicatech.com/"
)


print("COGNITO DOMAIN:", COGNITO_DOMAIN)
print("USER POOL ID:", USER_POOL_ID)
print("CLIENT ID:", CLIENT_ID)

print("REDIRECT URI:", REDIRECT_URI)
print("COGNITO LOGIN URL:", COGNITO_LOGIN_URL)

print("APP URL:", APP_URL)


AGENT_VERSION = os.environ.get("AGENT_VERSION", "v2")


mcp_config = None

if AGENT_VERSION == "v2":
    import json

    try:
        mcp_config = json.loads(open("mcp_config.json").read())
    except FileNotFoundError:
        mcp_config = json.loads(open("mcp_config_default.json").read())


CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
print("CORS_ORIGINS:", CORS_ORIGINS)


KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")

KEYCLOAK_AUTH_HOST = os.environ.get("KEYCLOAK_AUTH_HOST", "auth.arsmedicatech.com")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "arsmedicatech")
KEYCLOAK_BASE_URL = os.environ.get("KEYCLOAK_BASE_URL", f"https://{KEYCLOAK_AUTH_HOST}")

KEYCLOAK_SERVER_METADATA_URL = os.environ.get(
    "KEYCLOAK_SERVER_METADATA_URL",
    f"https://{KEYCLOAK_AUTH_HOST}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration",
)

FRONTEND_REDIRECT = os.environ.get("FRONTEND_REDIRECT", "http://localhost:3000")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

MINIO_ENCOUNTER_RECORDINGS_BUCKET = os.environ.get(
    "MINIO_ENCOUNTER_RECORDINGS_BUCKET", "encounter-recordings"
)


class Config:
    SURREALDB_NAMESPACE = SURREALDB_NAMESPACE
    SURREALDB_DATABASE = SURREALDB_DATABASE
    SURREALDB_USER = SURREALDB_USER
    SURREALDB_PASS = SURREALDB_PASS
    SURREALDB_PROTOCOL = SURREALDB_PROTOCOL
    SURREALDB_HOST = SURREALDB_HOST
    SURREALDB_PORT = SURREALDB_PORT
    SURREALDB_URL = SURREALDB_URL
    SURREALDB_ICD_DB = SURREALDB_ICD_DB
    ENCRYPTION_KEY = ENCRYPTION_KEY
    PORT = PORT
    DEBUG = DEBUG
    HOST = HOST
    NCBI_API_KEY = NCBI_API_KEY
    FLASK_SECRET_KEY = FLASK_SECRET_KEY
    BASE_URL = BASE_URL
    FHIR_BASE_URL = FHIR_BASE_URL
    FHIR_GATEWAY_URL = FHIR_GATEWAY_URL
    MCP_URL = MCP_URL
    OPTIMAL_URL = OPTIMAL_URL
    REDIS_HOST = REDIS_HOST
    REDIS_PORT = REDIS_PORT
    NOTIFICATIONS_CHANNEL = NOTIFICATIONS_CHANNEL
    UPLOADS_CHANNEL = UPLOADS_CHANNEL
    SENTRY_DSN = SENTRY_DSN
    DEMO_ADMIN_USERNAME = DEMO_ADMIN_USERNAME
    DEMO_ADMIN_PASSWORD = DEMO_ADMIN_PASSWORD
    BUCKET_NAME = BUCKET_NAME
    S3_AWS_ACCESS_KEY_ID = S3_AWS_ACCESS_KEY_ID
    S3_AWS_SECRET_ACCESS_KEY = S3_AWS_SECRET_ACCESS_KEY
    TEXTRACT_AWS_ACCESS_KEY_ID = TEXTRACT_AWS_ACCESS_KEY_ID
    TEXTRACT_AWS_SECRET_ACCESS_KEY = TEXTRACT_AWS_SECRET_ACCESS_KEY
    UMLS_API_KEY = UMLS_API_KEY
    ICD_AUTOCODER_URL = ICD_AUTOCODER_URL
    ICD_AUTOCODER_TIMEOUT = ICD_AUTOCODER_TIMEOUT
    ICD_AUTOCODER_RATE_LIMIT = ICD_AUTOCODER_RATE_LIMIT
    ICD_AUTOCODER_RATE_WINDOW = ICD_AUTOCODER_RATE_WINDOW
    ICD_AUTOCODER_FEEDBACK_TABLE = ICD_AUTOCODER_FEEDBACK_TABLE
    AWS_REGION = AWS_REGION
    COGNITO_DOMAIN = COGNITO_DOMAIN
    USER_POOL_ID = USER_POOL_ID
    CLIENT_ID = CLIENT_ID
    CLIENT_SECRET = CLIENT_SECRET
    LOGINRADIUS_SITE_URL = LOGINRADIUS_SITE_URL
    LOGINRADIUS_OIDC_APP_NAME = LOGINRADIUS_OIDC_APP_NAME
    LOGINRADIUS_CLIENT_ID = LOGINRADIUS_CLIENT_ID
    LOGINRADIUS_CLIENT_SECRET = LOGINRADIUS_CLIENT_SECRET
    REDIRECT_URI = REDIRECT_URI
    COGNITO_LOGIN_URL = COGNITO_LOGIN_URL
    LOGOUT_URI = LOGOUT_URI
    REACT_PORT = REACT_PORT
    APP_URL = APP_URL
    AGENT_VERSION = AGENT_VERSION
    CORS_ORIGINS = CORS_ORIGINS
    KEYCLOAK_CLIENT_ID = KEYCLOAK_CLIENT_ID
    KEYCLOAK_CLIENT_SECRET = KEYCLOAK_CLIENT_SECRET
    KEYCLOAK_AUTH_HOST = KEYCLOAK_AUTH_HOST
    KEYCLOAK_REALM = KEYCLOAK_REALM
    KEYCLOAK_BASE_URL = KEYCLOAK_BASE_URL
    KEYCLOAK_SERVER_METADATA_URL = KEYCLOAK_SERVER_METADATA_URL
    FRONTEND_REDIRECT = FRONTEND_REDIRECT
    MINIO_ENDPOINT = MINIO_ENDPOINT
    MINIO_ACCESS_KEY = MINIO_ACCESS_KEY
    MINIO_SECRET_KEY = MINIO_SECRET_KEY
    MINIO_ENCOUNTER_RECORDINGS_BUCKET = MINIO_ENCOUNTER_RECORDINGS_BUCKET

    @classmethod
    def as_dict(cls) -> dict:
        return {
            k: v
            for k, v in vars(cls).items()
            if not k.startswith("_") and not callable(v)
        }
