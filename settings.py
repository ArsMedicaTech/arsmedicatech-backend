""""""

import os
from os.path import dirname, join

from dotenv import load_dotenv

from lib.logger import Logger

logger: Logger = Logger()


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
KEYCLOAK_SERVER_METADATA_URL = os.environ.get("KEYCLOAK_SERVER_METADATA_URL", "")

KEYCLOAK_AUTH_HOST = os.environ.get("KEYCLOAK_AUTH_HOST", "auth.arsmedicatech.com")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "arsmedicatech")
KEYCLOAK_BASE_URL = os.environ.get("KEYCLOAK_BASE_URL", f"https://{KEYCLOAK_AUTH_HOST}")

FRONTEND_REDIRECT = os.environ.get("FRONTEND_REDIRECT", "http://localhost:3000")
