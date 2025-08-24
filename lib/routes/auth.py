"""
Auth routes for handling authentication with AWS Cognito and federated identity providers like Google.
"""

import base64
import secrets
from types import NoneType
from typing import Any, Dict, Optional, Tuple, TypedDict, Union, cast
from urllib import parse

import jwt
import requests
from flask import Response, jsonify, redirect, request, session
from requests import Response as RequestsResponse
from werkzeug.wrappers.response import Response as BaseResponse

from lib.models.user.user import User
from lib.services.user_service import CreateUserResult, UserService
from settings import (
    APP_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    COGNITO_DOMAIN,
    LOGOUT_URI,
    REDIRECT_URI,
    logger,
)


def generate_safe_username(email: str, sub: str) -> str:
    """
    Generate a safe username based on email or sub (Cognito subject ID).
    :param email: The user's email address.
    :param sub: The Cognito subject ID (unique identifier for the user).
    :return: A safe username string that is at least 3 characters long and no longer than 30 characters.
    """
    import re

    base = email.split("@")[0] if email else f"user_{sub[:8]}"

    # Strip invalid characters
    base = re.sub(r"[^a-zA-Z0-9_]", "_", base)

    # Pad if too short
    if len(base) < 3:
        base = f"{base}_{sub[:4]}"

    # Truncate if too long
    return base[:30]


def if_error(
    error: str, error_description: Optional[str]
) -> Union[Tuple[Response, int], BaseResponse]:
    decoded_description = parse.unquote(error_description or "")
    logger.warning("Cognito auth error: %s - %s", error, decoded_description)

    # Get intent from state parameter for error handling
    state = request.args.get("state", "patient:signin")
    if ":" in state:
        _, intent = state.split(":", 1)
    else:
        intent = "signin"  # Default to signin for backward compatibility

    # Handle specific Cognito errors
    if error == "invalid_request" and "email" in decoded_description.lower():
        # This is likely the "email cannot be updated" error
        logger.info("User attempted to sign up with existing email in Cognito")

        # Only show email error for signup intent
        if intent == "signup":
            # Redirect to frontend with error parameters
            error_url = f"{APP_URL}?error=invalid_request&error_description={parse.quote('Email already exists. Please try signing in instead.')}&suggested_action=login&intent=signup"
            return redirect(error_url)
        else:
            # For signin intent, this means the user exists in Cognito but there's a linking issue
            # This typically happens when:
            # 1. User was created via traditional registration (not Google)
            # 2. User is trying to sign in with Google for the first time
            # 3. Cognito can't link the accounts due to email-as-username configuration
            error_url = f"{APP_URL}?error=invalid_request&error_description={parse.quote('This email is associated with a traditional account. Please sign in with your username and password instead.')}&suggested_action=home&intent=signin"
            return redirect(error_url)

    # Handle other common Cognito errors
    if error == "access_denied":
        error_url = f"{APP_URL}?error=access_denied&error_description={parse.quote('Access was denied. Please try again.')}&suggested_action=home"
        return redirect(error_url)

    if error == "server_error":
        error_url = f"{APP_URL}?error=server_error&error_description={parse.quote('Authentication service is temporarily unavailable. Please try again later.')}&suggested_action=home"
        return redirect(error_url)

    if error == "temporarily_unavailable":
        error_url = f"{APP_URL}?error=temporarily_unavailable&error_description={parse.quote('Authentication service is temporarily unavailable. Please try again later.')}&suggested_action=home"
        return redirect(error_url)

    # Default error handling
    # Whitelist of allowed error types
    allowed_errors = {
        "invalid_request",
        "access_denied",
        "server_error",
        "temporarily_unavailable",
    }
    if error not in allowed_errors:
        logger.warning("Unrecognized error type: %s", error)
        error = "unknown_error"
        decoded_description = "An unknown error occurred."

    # Sanitize error_description
    sanitized_description = parse.quote(decoded_description)

    error_url = f"{APP_URL}?error={error}&error_description={sanitized_description}&suggested_action=home"
    return redirect(error_url)


def get_token(code: str) -> RequestsResponse:
    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"

    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}",
    }

    body: Dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(token_url, headers=headers, data=body)

    return response


class ErrorOnlyResponse(TypedDict):
    error: str


class ErrorResponse(TypedDict):
    error: str
    message: str


def return_jsonify_error(response: ErrorResponse, status: int) -> Tuple[Response, int]:
    jsonified = ErrorResponse(error=response["error"], message=response["message"])
    return jsonify(jsonified), status


def create_user(
    user_service: UserService, username: str, email: str, role_from_query: str
) -> Union[NoneType, Tuple[Response, int]]:
    # Create user with a random password (not used for federated login)
    random_password = secrets.token_urlsafe(16)

    result: CreateUserResult = cast(
        CreateUserResult,
        user_service.create_user(  # type: ignore
            username=username,
            email=email,
            password=random_password,
            first_name="",
            last_name="",
            role=role_from_query,
            is_federated=True,  # Mark as federated user
        ),
    )

    if (
        not result["success"]
        or not result["user"]
        or not getattr(result["user"], "id", None)
    ):
        logger.error(f"Failed to create user from federated login: {result['message']}")
        result_message = result["message"]
        return (
            jsonify({"error": "Failed to create user", "message": result_message}),
            500,
        )
    return None


def update_user(user_service: UserService, user: User, email: str):
    # User is signing in with existing account - this is fine
    # Note: If Cognito is still returning "email cannot be updated" error,
    # it means the Cognito configuration needs to be updated to remove
    # UsernameAttributes: [email] from the User Pool configuration
    logger.info(f"Existing user logged in via federated identity: {email}")
    # Optionally update user info if changed
    updates: Dict[str, Any] = {}
    if updates and user.id is not None:
        user_service.update_user(str(user.id), updates)


def get_user_response(
    tokens: Dict[str, str],
) -> Union[RequestsResponse, Tuple[Response, int]]:
    user_info_url = f"https://{COGNITO_DOMAIN}/oauth2/userInfo"
    headers = {"Authorization": f'Bearer {tokens["access_token"]}'}

    user_response = requests.get(user_info_url, headers=headers)

    if user_response.status_code != 200:
        logger.error(
            "Failed to fetch user info: %s - %s",
            user_response.status_code,
            user_response.text,
        )
        return (
            jsonify(
                {"status": user_response.status_code, "message": user_response.text}
            ),
            400,
        )
    else:
        return user_response


class Claims(TypedDict):
    email: str
    name: str
    sub: str
    cognito_username: str
    username: str
    exp: Optional[str]


def get_user_data_from_claims(id_token: str, user_info: Dict[str, Any]) -> Claims:
    claims: Claims = jwt.decode(id_token, options={"verify_signature": False})

    email = user_info.get("email") or claims.get("email") or ""
    name = user_info.get("name") or claims.get("name", "") or ""
    sub = claims.get("sub") or ""
    cognito_username = claims.get("cognito:username") or ""

    # Generate a fallback username
    username = (
        cognito_username if cognito_username else generate_safe_username(email, sub)
    )

    return Claims(
        {
            "email": email,
            "name": name,
            "sub": sub,
            "cognito_username": cognito_username,
            "username": username,
            "exp": claims.get("exp"),
        }
    )


def _handle_existing_user(
    user: User, intent: str, user_service: UserService, claims: Claims
) -> Optional[ErrorResponse]:
    """Handles logic for a user that already exists in the database."""
    if intent == "signup":
        logger.info(f"User attempted to sign up with existing email: {claims['email']}")
        error_url = f"{APP_URL}?error=invalid_request&error_description={parse.quote('This email address is already registered.')}"
        return redirect(error_url)
    else:
        # It's a sign-in, so update their info from the claims
        update_user(user_service, user, claims["email"])
        return None  # Return None on success


def _handle_new_user(
    user_service: UserService, claims: Claims, role_from_query: str
) -> Union[NoneType, Tuple[Response, int]]:
    """Creates a new federated user in the database."""
    # The create_user function should return the created User object or an error
    new_user_or_error: Union[NoneType, Tuple[Response, int]] = create_user(
        user_service,
        username=claims["username"],
        email=claims["email"],
        role_from_query=role_from_query,
    )

    if isinstance(new_user_or_error, User):
        logger.info(f"User created successfully: {claims['email']}")
        return new_user_or_error
    else:
        # create_user returned an error
        logger.error(f"Failed to create user: {claims['email']}")
        return new_user_or_error


def get_or_create_user(
    user_service: UserService,
    claims: Claims,
    role: str,
    intent: str,
) -> Union[User, Union[NoneType, Tuple[Response, int]], Optional[ErrorResponse]]:
    """
    Gets a user by email. If they exist, handles update or conflict.
    If they don't exist, creates them.
    """
    user = user_service.get_user_by_email(claims["email"])

    if user:
        # User exists, handle sign-in or sign-up conflict
        error = _handle_existing_user(user, intent, user_service, claims)
        if error:
            return error
        return user  # Return the existing user on success
    else:
        # User does not exist, create them
        return _handle_new_user(user_service, claims, role)


def cognito_login_route() -> Union[Tuple[Response, int], BaseResponse]:
    # 1. Handle initial errors from Cognito
    error = request.args.get("error")
    if error:
        error_description = request.args.get("error_description")
        return if_error(error, error_description)

    # 2. Get authorization code
    code = request.args.get("code")
    if not code:
        logger.error("No authorization code provided")
        return jsonify({"error": "No authorization code provided"}), 400

    # (Let's assume get_token, get_user_response etc. are refactored into helpers
    # that raise exceptions on failure for clarity)
    try:
        tokens = get_token(code)
        user_info: Claims = get_user_data_from_claims(tokens["id_token"])
        claims = get_user_data_from_claims(tokens["id_token"], user_info)
    except Exception as e:
        logger.error(f"Failed during token exchange or user info retrieval: {e}")
        return jsonify({"error": "Authentication failed"}), 500

    # 3. Parse state to get role and intent
    state = request.args.get("state", "patient:signin")
    role_from_query, intent = state.split(":", 1) if ":" in state else (state, "signin")

    # 4. Get or Create the User
    user_service = UserService()
    user_service.connect()
    try:
        user_or_error = get_or_create_user(
            user_service, claims, role_from_query, intent
        )

        # --- TYPE NARROWING ---
        # We explicitly check the type of the return value.
        if not isinstance(user_or_error, User):
            # MyPy knows this is an ErrorResponse, so we can return it.
            return user_or_error

        # From this point on, MyPy knows we have a valid User object.
        user = user_or_error

        if not user.id:
            logger.error("User ID is missing after creation/retrieval")
            return jsonify({"error": "User ID is missing"}), 500

        # 5. Create Session and Redirect on Success
        session["user_id"] = user.id
        session["auth_token"] = tokens["id_token"]

        user_service.create_session(
            user_id=user.id,
            username=user.username,
            role=role_from_query,
            session_token=tokens["id_token"],
            expires_at=claims["exp"],
        )
        session.modified = True

        success_url = f"{APP_URL}?auth_success=true&token={session['auth_token']}&user_id={user.id}&username={user.username}&role={role_from_query}"
        return redirect(success_url)

    except Exception as e:
        logger.error(f"Unhandled error in user processing: {e}")
        return redirect(APP_URL + "?error=server_error")
    finally:
        user_service.close()


def auth_logout_route() -> BaseResponse:
    session.clear()

    logout_url = (
        f"https://{COGNITO_DOMAIN}/logout?"
        f"client_id={CLIENT_ID}&"
        f"logout_uri={parse.quote(LOGOUT_URI)}"
    )

    return redirect(logout_url)
