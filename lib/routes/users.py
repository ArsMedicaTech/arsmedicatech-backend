"""
User management routes for the application.
"""

from typing import Any, Dict, List, Tuple

from flask import Response, jsonify, request, session

from lib.models.user.user import User
from lib.services.auth_decorators import get_current_user, get_current_user_id
from lib.services.openai_security import get_openai_security_service
from lib.services.user_service import CreateUserResult, UserService
from settings import logger


def search_users_route() -> Tuple[Response, int]:
    """
    Search for users (authenticated users only)

    This endpoint allows authenticated users to search for other users
    by username, first name, last name, or email. It excludes inactive users
    and the current user from the results. The search query is case-insensitive
    and can be a partial match on any of the searchable fields.
    Returns a JSON response with a list of matching users, limited to 20 results.
    The response includes user details such as ID, username, email, first name,
    last name, role, display name, and avatar URL.

    Example request:
    GET /api/users/search?q=example
    Query parameters:
    - q: The search query string to filter users by username, first name,
         last name, or email.
    Example response:
    ...

    :return: Response object containing a JSON list of users matching the search query.
    """
    logger.debug("User search request received")
    query = request.args.get("q", "").strip()
    logger.debug(f"Search query: '{query}'")

    user_service = UserService()
    user_service.connect()
    try:
        # Get all users and filter by search query
        all_users = user_service.get_all_users()

        # Filter users based on search query
        filtered_users: List[Dict[str, str]] = []
        for user in all_users:
            # Skip inactive users
            if not user.is_active:
                continue

            # Skip the current user
            current_user = get_current_user()
            if current_user and user.id == current_user.user_id:
                continue

            # Search in username, first_name, last_name, and email
            searchable_text = f"{user.username} {user.first_name or ''} {user.last_name or ''} {user.email or ''}".lower()

            if not query or query.lower() in searchable_text:
                filtered_users.append(
                    {
                        "id": str(user.id) if user.id is not None else "",
                        "username": user.username or "",
                        "email": user.email or "",
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "role": user.role or "",
                        "display_name": (
                            f"{user.first_name or ''} {user.last_name or ''}".strip()
                            or (user.username or "")
                        ),
                        "avatar": f"https://ui-avatars.com/api/?name={user.first_name or user.username or ''}&background=random",
                    }
                )

        # Limit results to 20 users
        filtered_users = filtered_users[:20]

        return jsonify({"users": filtered_users, "total": len(filtered_users)}), 200

    finally:
        user_service.close()


def check_users_exist_route() -> Tuple[Response, int]:
    """
    Check if any users exist (public endpoint)

    This endpoint checks if there are any users in the database.
    It returns a JSON response indicating whether users exist and the count of users.
    Example request:
    GET /api/users/check_exists
    Example response:
    {
        "users_exist": true,
        "user_count": 5
    }

    :return: Response object containing a JSON indicating if users exist and the count of users.
    """
    user_service = UserService()
    user_service.connect()
    try:
        users = user_service.get_all_users()
        logger.debug(f"Found {len(users)} users in database")
        for user in users:
            logger.debug(
                f"User: {user.username} (ID: {user.id}, Role: {user.role}, Active: {user.is_active})"
            )
        return jsonify({"users_exist": len(users) > 0, "user_count": len(users)}), 200
    finally:
        user_service.close()


def setup_default_admin_route() -> Tuple[Response, int]:
    """
    Setup default admin user (only works if no users exist)

    This endpoint creates a default admin user if no users exist in the database.
    It is intended to be used during the initial setup of the application.
    Example request:
    POST /api/users/setup_default_admin
    Example response:
    {
        "message": "Default admin user created successfully"
    }

    :return: Response object containing a JSON message indicating success or failure.
    """
    user_service = UserService()
    user_service.connect()
    try:
        success, message = user_service.create_default_admin()
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    finally:
        user_service.close()


def activate_user_route(user_id: str) -> Tuple[Response, int]:
    """
    Activate a user account (admin only)

    This endpoint allows an admin to activate a user account by user ID.
    Example request:
    POST /api/users/activate/<user_id>
    Path parameters:
    - user_id: The ID of the user to activate.
    Example response:
    {
        "message": "User activated successfully"
    }

    :param user_id: The ID of the user to activate.
    :return: Response object containing a JSON message indicating success or failure.
    """
    user_service = UserService()
    user_service.connect()
    try:
        success, message = user_service.activate_user(user_id)
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    finally:
        user_service.close()


def deactivate_user_route(user_id: str) -> Tuple[Response, int]:
    """
    Deactivate a user account (admin only)

    This endpoint allows an admin to deactivate a user account by user ID.
    Example request:
    POST /api/users/deactivate/<user_id>
    Path parameters:
    - user_id: The ID of the user to deactivate.
    Example response:
    {
        "message": "User deactivated successfully"
    }

    :param user_id: The ID of the user to deactivate.
    :return: Response object containing a JSON message indicating success or failure.
    """
    user_service = UserService()
    user_service.connect()
    try:
        success, message = user_service.deactivate_user(user_id)
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    finally:
        user_service.close()


def get_all_users_route() -> Tuple[Response, int]:
    """
    Get all users (admin only)

    This endpoint retrieves a list of all users in the system.
    It is intended for administrative use and returns user details such as ID,
    username, email, first name, last name, role, active status, and creation date.
    Example request:
    GET /api/users/all
    Example response:
    []

    :return: Response object containing a JSON list of all users.
    """
    user_service = UserService()
    user_service.connect()
    try:
        users = user_service.get_all_users()
        return (
            jsonify(
                {
                    "users": [
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                            "role": user.role,
                            "is_active": user.is_active,
                            "created_at": user.created_at,
                        }
                        for user in users
                    ]
                }
            ),
            200,
        )
    finally:
        user_service.close()


def change_password_route() -> Tuple[Response, int]:
    """
    Change user password
    This endpoint allows the authenticated user to change their password.
    It requires the current password and the new password to be provided in the request body.
    Example request:
    POST /api/users/change_password
    Body:
    {
        "current_password": "old_password",
        "new_password": "new_password"
    }
    Example response:
    {
        "message": "Password changed successfully"
    }

    :return: Response object containing a JSON message indicating success or failure.
    """
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not all([current_password, new_password]):
        return jsonify({"error": "Current password and new password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        success, message = user_service.change_password(
            user_id, current_password, new_password
        )

        assert isinstance(success, bool), "Success should be a boolean"

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    finally:
        user_service.close()


def get_current_user_info_route() -> Tuple[Response, int]:
    """
    Get current authenticated user information

    This endpoint retrieves the information of the currently authenticated user.
    It returns details such as user ID, username, email, first name, last name,
    role, active status, and creation date.
    Example request:
    GET /api/users/me
    Example response:
    {}

    :return: Response object containing a JSON representation of the current user's information.
    """
    user_service = UserService()
    user_service.connect()
    try:
        current_user = get_current_user()

        if not current_user:
            return jsonify({"error": "Authentication required"}), 401

        user_id = current_user.user_id
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        user = user_service.get_user_by_id(user_id)
        if user:
            return (
                jsonify(
                    {
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                            "role": user.role,
                            "is_active": user.is_active,
                            "created_at": user.created_at,
                        }
                    }
                ),
                200,
            )
        else:
            return jsonify({"error": "User not found"}), 404
    finally:
        user_service.close()


def logout_route() -> Tuple[Response, int]:
    """
    Logout user and invalidate session

    This endpoint logs out the user by invalidating their session token.
    It removes the authentication token from the session and calls the user service
    to perform any necessary cleanup on the server side.
    Example request:
    POST /api/users/logout
    Example response:
    {
        "message": "Logged out successfully"
    }

    :return: Response object containing a JSON message indicating successful logout.
    """
    from typing import Optional

    token = session.get("auth_token", "")
    token_str: Optional[str] = str(token) if token is not None else None
    if token_str:
        user_service = UserService()
        user_service.connect()
        try:
            user_service.logout(token_str)
        finally:
            user_service.close()

    session.pop("auth_token", None)
    return jsonify({"message": "Logged out successfully"}), 200


def login_route() -> Tuple[Response, int]:
    """
    Authenticate user and create session

    This endpoint allows users to log in by providing their username and password.
    It validates the credentials, creates a user session, and returns a JSON response
    containing the authentication token and user details.
    Example request:
    POST /api/users/login
    Body:
    {
        "username": "user1",
        "password": "securepassword"
    }
    Example response:
    {}

    :return: Response object containing a JSON representation of the user session and token.
    """
    logger.debug("Login request received")
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username")
    password = data.get("password")

    logger.debug(f"Login attempt for username: {username}")

    if not all([username, password]):
        return jsonify({"error": "Username and password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        success, message, user_session = user_service.authenticate_user(
            username, password
        )

        logger.debug(f"Authentication result - success: {success}, message: {message}")

        if success:
            assert (
                user_session is not None
            ), "User session should not be None on successful authentication"

            # Store token and user_id in session
            session["auth_token"] = user_session.session_token
            session["user_id"] = user_session.user_id
            logger.debug(f"Stored session token: {user_session.session_token[:10]}...")
            logger.debug(f"Stored session user_id: {user_session.user_id}")

            return (
                jsonify(
                    {
                        "message": message,
                        "token": user_session.session_token,
                        "user": {
                            "id": user_session.user_id,
                            "username": user_session.username,
                            "role": user_session.role,
                        },
                    }
                ),
                200,
            )
        else:
            return jsonify({"error": message}), 401
    finally:
        user_service.close()


def register_route() -> Tuple[Response, int]:
    """
    Register a new user account

    This endpoint allows new users to register by providing their username,
    email, password, and optional first name, last name, and role.
    Example request:
    POST /api/users/register
    Body:
    {}

    Example response:
    {}

    :return: Response object containing a JSON representation of the newly created user or an error message.
    """
    logger.debug("Registration request received")
    data = request.json
    logger.debug(f"Registration data: {data}")
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    role = data.get("role", "patient")
    logger.debug(
        f"[DEBUG] Registration fields - username: {username}, email: {email}, first_name: {first_name}, last_name: {last_name}, role: {role}"
    )

    if not all([username, email, password]):
        return jsonify({"error": "Username, email, and password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        logger.debug("Calling user_service.create_user")
        create_user_result: CreateUserResult = user_service.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
        )

        logger.debug(
            f"User creation result - success: {create_user_result['success']}, message: {create_user_result['message']}"
        )
        if create_user_result["success"]:
            if not create_user_result["user"]:
                logger.error("User creation succeeded but returned user is None")
                return jsonify({"error": "User creation failed"}), 500

            logger.debug(f"User created successfully: {create_user_result['user'].id}")
            return (
                jsonify(
                    {
                        "message": create_user_result["message"],
                        "user": {
                            "id": create_user_result["user"].id,
                            "username": create_user_result["user"].username,
                            "email": create_user_result["user"].email,
                            "first_name": create_user_result["user"].first_name,
                            "last_name": create_user_result["user"].last_name,
                            "role": create_user_result["user"].role,
                        },
                    }
                ),
                201,
            )
        else:
            logger.debug(f"User creation failed: {create_user_result['message']}")
            return jsonify({"error": create_user_result["message"]}), 400
    finally:
        user_service.close()


def settings_route() -> Tuple[Response, int]:
    """
    Handle settings requests

    This endpoint allows users to get or update their settings.
    It supports both GET and POST methods:
    - GET: Retrieve the current user's settings.
    - POST: Update the current user's settings, such as OpenAI API key.
    Example request:
    GET /api/users/settings
    POST /api/users/settings
    Body:
    {
        "openai_api_key": "sk-..."
    }
    Example response:
    {
        "success": true,
        "settings": {
            "user_id": "12345",
            "has_openai_api_key": true,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-02T00:00:00Z"
        }
    }

    :return: Response object containing a JSON representation of the user's settings or an error message.
    """
    if request.method == "GET":
        return get_user_settings()
    elif request.method == "POST":
        return update_user_settings()
    else:
        return jsonify({"error": "Method not allowed"}), 405


def get_user_settings() -> Tuple[Response, int]:
    """
    Get current user's settings

    This endpoint retrieves the settings for the currently authenticated user.
    It returns a JSON response containing the user ID, whether the user has an OpenAI API key,
    and timestamps for when the settings were created and last updated.
    Example request:
    GET /api/users/settings
    Example response:
    {
        "success": true,
        "settings": {
            "user_id": "12345",
            "has_openai_api_key": true,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-02T00:00:00Z"
        }
    }

    :return: Response object containing a JSON representation of the user's settings or an error message.
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        user_service = UserService()
        user_service.connect()
        try:
            settings = user_service.get_user_settings(user_id)
            if not settings:
                return jsonify({"error": "Failed to load settings"}), 500

            # Return settings without exposing the API keys
            return (
                jsonify(
                    {
                        "success": True,
                        "settings": {
                            "user_id": settings.user_id,
                            "has_openai_api_key": settings.has_openai_api_key(),
                            "has_optimal_api_key": settings.has_optimal_api_key(),
                            "created_at": settings.created_at,
                            "updated_at": settings.updated_at,
                        },
                    }
                ),
                200,
            )
        finally:
            user_service.close()

    except Exception as e:
        logger.error(f"Error getting user settings: {e}")
        return jsonify({"error": "Internal server error"}), 500


def update_user_settings() -> Tuple[Response, int]:
    """
    Update user settings

    This endpoint allows the authenticated user to update their settings,
    such as the OpenAI API key. It expects a JSON payload with the new settings.
    Example request:
    POST /api/users/settings
    Body:
    {
        "openai_api_key": "sk-..."
    }
    Example response:
    {
        "success": true,
        "message": "OpenAI API key updated successfully"
    }

    :return: Response object containing a JSON message indicating success or failure.
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        logger.debug(f"Updating settings for user: {user_id}")
        logger.debug(f"Request data: {data}")

        user_service = UserService()
        user_service.connect()
        try:
            # Handle OpenAI API key update
            if "openai_api_key" in data:
                api_key = data["openai_api_key"]
                logger.debug(f"Updating OpenAI API key for user {user_id}")
                logger.debug(f"API key length: {len(api_key) if api_key else 0}")
                logger.debug(
                    f"API key starts with sk-: {api_key.startswith('sk-') if api_key else False}"
                )

                success, message = user_service.update_openai_api_key(user_id, api_key)
                logger.debug(f"Update result: success={success}, message={message}")

                if success:
                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": "OpenAI API key updated successfully",
                            }
                        ),
                        200,
                    )
                else:
                    return jsonify({"error": message}), 400

            # Handle Optimal API key update
            if "optimal_api_key" in data:
                api_key = data["optimal_api_key"]
                logger.debug(f"Updating Optimal API key for user {user_id}")
                logger.debug(f"API key length: {len(api_key) if api_key else 0}")

                success, message = user_service.update_optimal_api_key(user_id, api_key)
                logger.debug(f"Update result: success={success}, message={message}")

                if success:
                    return (
                        jsonify(
                            {
                                "success": True,
                                "message": "Optimal API key updated successfully",
                            }
                        ),
                        200,
                    )
                else:
                    return jsonify({"error": message}), 400

            return jsonify({"error": "No valid settings to update"}), 400

        finally:
            user_service.close()

    except Exception as e:
        logger.error(f"Error updating user settings: {e}")
        return jsonify({"error": "Internal server error"}), 500


def get_api_usage_route() -> Tuple[Response, int]:
    """
    Get current user's API usage statistics

    This endpoint retrieves the API usage statistics for the currently authenticated user.
    It returns a JSON response containing the user's API usage data, such as the number of requests made,
    tokens used, and any other relevant metrics.
    Example request:
    GET /api/users/api_usage
    Example response:
    {
        "success": true,
        "usage": {
            "requests_made": 100,
            "tokens_used": 5000,
            "last_reset": "2023-01-01T00:00:00Z"
        }
    }

    :return: Response object containing a JSON representation of the user's API usage statistics or an error message.
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        security_service = get_openai_security_service()
        usage_stats = security_service.get_usage_stats(user_id)

        return jsonify({"success": True, "usage": usage_stats}), 200

    except Exception as e:
        logger.error(f"Error getting API usage: {e}")
        return jsonify({"error": "Internal server error"}), 500


def get_user_profile_route() -> Tuple[Response, int]:
    """
    Get current user's profile information

    This endpoint retrieves the profile information of the currently authenticated user.
    It returns a JSON response containing the user's ID, username, email, first name, last name,
    role, specialty, clinic name, clinic address, phone number, active status, and creation date.
    Example request:
    GET /api/users/profile
    Example response:
    {}

    :return: Response object containing a JSON representation of the user's profile or an error message.
    """
    try:
        user_id = get_current_user_id()
        logger.debug(f"get_user_profile_route - user_id: {user_id}")
        if not user_id:
            logger.debug("No user_id found")
            return jsonify({"error": "Authentication required"}), 401

        user_service = UserService()
        user_service.connect()
        try:
            logger.debug(f"Getting user by ID: {user_id}")
            user = user_service.get_user_by_id(user_id)
            logger.debug(f"User lookup result: {user}")
            if not user:
                logger.debug("User not found")
                return jsonify({"error": "User not found"}), 404

            profile_data: Dict[str, Any] = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "specialty": user.specialty,
                "clinic_name": user.clinic_name,
                "clinic_address": user.clinic_address,
                "phone": user.phone,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
            logger.debug(f"Returning profile data: {profile_data}")

            return jsonify({"success": True, "profile": profile_data}), 200
        finally:
            user_service.close()

    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        return jsonify({"error": "Internal server error"}), 500


def update_user_profile_route() -> Tuple[Response, int]:
    """
    Update current user's profile information

    This endpoint allows the authenticated user to update their profile information.
    It expects a JSON payload with the fields to be updated, such as first name,
    last name, phone number, specialty, clinic name, clinic address, and role.
    Example request:
    POST /api/users/profile
    Body:
    {
        "first_name": "John",
        "last_name": "Doe",
        "phone": "+1234567890",
        "specialty": "Cardiology",
        "clinic_name": "Heart Clinic",
        "clinic_address": "123 Heart St, Cardiology City",
        "role": "provider"
    }
    Example response:
    {
        "success": true,
        "message": "Profile updated successfully"
    }

    :return: Response object containing a JSON message indicating success or failure.
    """
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        logger.debug(f"Updating profile for user: {user_id}")
        logger.debug(f"Request data: {data}")

        user_service = UserService()
        user_service.connect()
        try:
            # Prepare updates
            updates: Dict[str, Any] = {}

            # Basic profile fields
            if "first_name" in data:
                updates["first_name"] = data["first_name"]
            if "last_name" in data:
                updates["last_name"] = data["last_name"]
            if "phone" in data:
                # Validate phone number
                valid, msg = User.validate_phone(data["phone"])
                if not valid:
                    return jsonify({"error": msg}), 400
                updates["phone"] = data["phone"]

            # Provider-specific fields
            if "specialty" in data:
                updates["specialty"] = data["specialty"]
            if "clinic_name" in data:
                updates["clinic_name"] = data["clinic_name"]
            if "clinic_address" in data:
                updates["clinic_address"] = data["clinic_address"]

            # Role updates (admin only)
            if "role" in data:
                current_user = user_service.get_user_by_id(user_id)
                if not current_user or not current_user.is_admin():
                    return jsonify({"error": "Only admins can change roles"}), 403

                valid, msg = User.validate_role(data["role"])
                if not valid:
                    return jsonify({"error": msg}), 400
                updates["role"] = data["role"]

            if not updates:
                return jsonify({"error": "No valid fields to update"}), 400

            update_result = user_service.update_user(user_id, updates)
            logger.debug(f"Update result: {update_result}")

            if update_result["success"]:
                return (
                    jsonify(
                        {"success": True, "message": "Profile updated successfully"}
                    ),
                    200,
                )
            else:
                return jsonify({"error": update_result["message"]}), 400

        finally:
            user_service.close()

    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        return jsonify({"error": "Internal server error"}), 500
