"""
LoginRadius OIDC authentication routes.
"""

from typing import Tuple, cast

from flask import Response, jsonify, request, session

from lib.models.user.user import UserRoles
from lib.services.loginradius_service import LoginRadiusService
from lib.services.user_service import UserService
from settings import APP_URL, logger


def verify_loginradius_token_route() -> Tuple[Response, int]:
    """
    Verify LoginRadius ID token and create/update user session.

    This endpoint handles the verification of LoginRadius ID tokens and creates
    or updates user accounts in the system. It's called by the frontend after
    successful LoginRadius authentication.

    Example request:
    POST /api/auth/loginradius/verify
    Body:
    {
        "id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
        "access_token": "access_token_here",
        "role": "patient"
    }

    Example response:
    {
        "success": true,
        "token": "session_token_here",
        "user": {
            "id": "user_id",
            "username": "username",
            "email": "user@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "role": "patient",
            "auth_provider": "loginradius"
        }
    }

    :return: Response object containing authentication result
    """
    logger.debug("LoginRadius token verification request received")

    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    id_token = data.get("id_token")
    access_token = data.get("access_token")
    role = data.get("role", "patient")

    if not id_token:
        return jsonify({"error": "ID token is required"}), 400

    # Validate role
    if role not in ["patient", "provider", "admin"]:
        return jsonify({"error": "Invalid role specified"}), 400

    # Initialize services
    loginradius_service = LoginRadiusService()
    user_service = UserService()
    user_service.connect()

    try:
        # Verify LoginRadius ID token
        is_valid, user_info, error = loginradius_service.get_user_info_from_token(
            id_token, access_token
        )
        if not is_valid:
            logger.error(f"LoginRadius token verification failed: {error}")
            return jsonify({"error": f"Token verification failed: {error}"}), 401

        # Validate user_info and extract external_id
        if not user_info or not isinstance(user_info, dict):
            logger.error("LoginRadius returned no user info or unexpected format")
            return jsonify({"error": "No user information in token"}), 401

        # Prefer "sub" but fallback to other common fields, then ensure it's a string
        external_id = user_info.get("sub") or user_info.get("id") or None
        if not external_id:
            logger.error("External ID (sub) missing in LoginRadius user info")
            return jsonify({"error": "External user ID is missing"}), 401

        # Check if user exists by external_id
        existing_user = user_service.get_user_by_external_id(
            external_id=str(external_id), auth_provider="loginradius"
        )

        if existing_user:
            # Update existing user
            logger.debug(f"Updating existing LoginRadius user: {user_info['sub']}")
            updated_user = loginradius_service.update_user_from_loginradius(
                existing_user, user_info
            )

            # Save updated user
            if updated_user.id:
                user_service.update_user(str(updated_user.id), updated_user.to_dict())
                user = updated_user
            else:
                return jsonify({"error": "User ID missing after update"}), 500
        else:
            # Create new user
            logger.debug(f"Creating new LoginRadius user: {user_info['sub']}")
            new_user = loginradius_service.create_user_from_loginradius(
                user_info, cast(UserRoles, role)
            )

            # Save new user
            create_result = user_service.create_user(
                username=new_user.username,
                email=new_user.email,
                password="",  # No password for OAuth users; use empty string to satisfy create_user signature
                first_name=new_user.first_name,
                last_name=new_user.last_name,
                role=new_user.role,
                is_federated=True,
                auth_provider="loginradius",
                external_id=new_user.external_id,
                external_data=new_user.external_data,
            )

            if not create_result["success"] or not create_result["user"]:
                logger.error(
                    f"Failed to create LoginRadius user: {create_result['message']}"
                )
                return (
                    jsonify(
                        {"error": f"User creation failed: {create_result['message']}"}
                    ),
                    500,
                )

            user = create_result["user"]

        if not user.id:
            logger.error("User ID is missing after creation/update")
            return jsonify({"error": "User ID is missing"}), 500

        # Create session
        logger.debug(f"Creating session for LoginRadius user: {user.username}")
        session_token = loginradius_service._generate_session_token()

        user_session = user_service.create_session(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_token=session_token,
        )

        if not user_session:
            logger.error("Failed to create user session")
            return jsonify({"error": "Failed to create user session"}), 500

        # Store session data
        session["auth_token"] = session_token
        session["user_id"] = user.id
        session.modified = True

        logger.debug(f"LoginRadius authentication successful for user: {user.username}")

        return (
            jsonify(
                {
                    "success": True,
                    "token": session_token,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "role": user.role,
                        "auth_provider": user.auth_provider,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Unexpected error in LoginRadius authentication: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        user_service.close()


def loginradius_logout_route() -> Tuple[Response, int]:
    """
    Handle LoginRadius logout.

    This endpoint handles logout for LoginRadius users. It clears the session
    and optionally revokes tokens with LoginRadius.

    Example request:
    POST /api/auth/loginradius/logout
    Body:
    {
        "access_token": "access_token_here"  # Optional
    }

    Example response:
    {
        "success": true,
        "message": "Logged out successfully"
    }

    :return: Response object containing logout result
    """
    logger.debug("LoginRadius logout request received")

    data = request.json or {}
    access_token = data.get("access_token")

    # Clear session
    session.clear()

    # Optionally revoke tokens with LoginRadius
    if access_token:
        loginradius_service = LoginRadiusService()
        success, message = loginradius_service.revoke_tokens(access_token)

        if not success:
            logger.warning(f"Failed to revoke LoginRadius tokens: {message}")
            # Don't fail the logout if token revocation fails

    logger.debug("LoginRadius logout successful")

    return jsonify({"success": True, "message": "Logged out successfully"}), 200


def get_loginradius_config_route() -> Tuple[Response, int]:
    """
    Get LoginRadius configuration for frontend.

    This endpoint provides the necessary configuration information for the
    frontend to initialize LoginRadius OIDC authentication.

    Example response:
    {
        "site_url": "https://your-site-url.hub.loginradius.com",
        "oidc_app_name": "your-oidc-app-name",
        "client_id": "your-client-id",
        "redirect_uri": "http://localhost:3000/auth/callback"
    }

    :return: Response object containing LoginRadius configuration
    """
    from settings import (
        LOGINRADIUS_CLIENT_ID,
        LOGINRADIUS_OIDC_APP_NAME,
        LOGINRADIUS_SITE_URL,
    )

    config = {
        "site_url": LOGINRADIUS_SITE_URL,
        "oidc_app_name": LOGINRADIUS_OIDC_APP_NAME,
        "client_id": LOGINRADIUS_CLIENT_ID,
        "redirect_uri": f"{APP_URL}auth/callback",  # Frontend callback URL
    }

    return jsonify(config), 200
