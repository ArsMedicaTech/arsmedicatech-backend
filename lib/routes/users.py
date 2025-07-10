""""""
from flask import jsonify, request, session

from lib.services.auth_decorators import get_current_user, get_current_user_id
from lib.services.user_service import UserService
from lib.services.openai_security import get_openai_security_service


def search_users_route():
    """Search for users (authenticated users only)"""
    print("[DEBUG] User search request received")
    query = request.args.get('q', '').strip()
    print(f"[DEBUG] Search query: '{query}'")

    user_service = UserService()
    user_service.connect()
    try:
        # Get all users and filter by search query
        all_users = user_service.get_all_users()

        # Filter users based on search query
        filtered_users = []
        for user in all_users:
            # Skip inactive users
            if not user.is_active:
                continue

            # Skip the current user
            if user.id == get_current_user().user_id:
                continue

            # Search in username, first_name, last_name, and email
            searchable_text = f"{user.username} {user.first_name or ''} {user.last_name or ''} {user.email or ''}".lower()

            if not query or query.lower() in searchable_text:
                filtered_users.append({
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "display_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                    "avatar": f"https://ui-avatars.com/api/?name={user.first_name or user.username}&background=random"
                })

        # Limit results to 20 users
        filtered_users = filtered_users[:20]

        return jsonify({
            "users": filtered_users,
            "total": len(filtered_users)
        }), 200

    finally:
        user_service.close()

def check_users_exist_route():
    """Check if any users exist (public endpoint)"""
    user_service = UserService()
    user_service.connect()
    try:
        users = user_service.get_all_users()
        print(f"[DEBUG] Found {len(users)} users in database")
        for user in users:
            print(f"[DEBUG] User: {user.username} (ID: {user.id}, Role: {user.role}, Active: {user.is_active})")
        return jsonify({"users_exist": len(users) > 0, "user_count": len(users)})
    finally:
        user_service.close()


def setup_default_admin_route():
    """Setup default admin user (only works if no users exist)"""
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

def activate_user_route(user_id):
    """Activate a user account (admin only)"""
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

def deactivate_user_route(user_id):
    """Deactivate a user account (admin only)"""
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

def get_all_users_route():
    """Get all users (admin only)"""
    user_service = UserService()
    user_service.connect()
    try:
        users = user_service.get_all_users()
        return jsonify({
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at
                }
                for user in users
            ]
        }), 200
    finally:
        user_service.close()

def change_password_route():
    """Change user password"""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not all([current_password, new_password]):
        return jsonify({"error": "Current password and new password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        success, message = user_service.change_password(
            get_current_user().user_id,
            current_password,
            new_password
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400
    finally:
        user_service.close()

def get_current_user_info_route():
    """Get current authenticated user information"""
    user_service = UserService()
    user_service.connect()
    try:
        user = user_service.get_user_by_id(get_current_user().user_id)
        if user:
            return jsonify({
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at
                }
            }), 200
        else:
            return jsonify({"error": "User not found"}), 404
    finally:
        user_service.close()

def logout_route():
    """Logout user and invalidate session"""
    token = session.get('auth_token')
    if token:
        user_service = UserService()
        user_service.connect()
        try:
            user_service.logout(token)
        finally:
            user_service.close()

    session.pop('auth_token', None)
    return jsonify({"message": "Logged out successfully"}), 200

def login_route():
    """Authenticate user and create session"""
    print("[DEBUG] Login request received")
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get('username')
    password = data.get('password')

    print(f"[DEBUG] Login attempt for username: {username}")

    if not all([username, password]):
        return jsonify({"error": "Username and password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        success, message, user_session = user_service.authenticate_user(username, password)

        print(f"[DEBUG] Authentication result - success: {success}, message: {message}")

        if success:
            # Store token and user_id in session
            session['auth_token'] = user_session.token
            session['user_id'] = user_session.user_id
            print(f"[DEBUG] Stored session token: {user_session.token[:10]}...")
            print(f"[DEBUG] Stored session user_id: {user_session.user_id}")

            return jsonify({
                "message": message,
                "token": user_session.token,
                "user": {
                    "id": user_session.user_id,
                    "username": user_session.username,
                    "role": user_session.role
                }
            }), 200
        else:
            return jsonify({"error": message}), 401
    finally:
        user_service.close()

def register_route():
    """Register a new user account"""
    print("[DEBUG] Registration request received")
    data = request.json
    print(f"[DEBUG] Registration data: {data}")
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    role = data.get('role', 'patient')
    print(
        f"[DEBUG] Registration fields - username: {username}, email: {email}, first_name: {first_name}, last_name: {last_name}, role: {role}")

    if not all([username, email, password]):
        return jsonify({"error": "Username, email, and password are required"}), 400

    user_service = UserService()
    user_service.connect()
    try:
        print("[DEBUG] Calling user_service.create_user")
        success, message, user = user_service.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role
        )

        print(f"[DEBUG] User creation result - success: {success}, message: {message}")
        if success:
            print(f"[DEBUG] User created successfully: {user.id}")
            return jsonify({
                "message": message,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role
                }
            }), 201
        else:
            print(f"[DEBUG] User creation failed: {message}")
            return jsonify({"error": message}), 400
    finally:
        user_service.close()



def settings_route():
    """Handle settings requests"""
    if request.method == 'GET':
        return get_user_settings()
    elif request.method == 'POST':
        return update_user_settings()
    else:
        return jsonify({"error": "Method not allowed"}), 405


def get_user_settings():
    """Get current user's settings"""
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

            # Return settings without exposing the API key
            return jsonify({
                "success": True,
                "settings": {
                    "user_id": settings.user_id,
                    "has_openai_api_key": settings.has_openai_api_key(),
                    "created_at": settings.created_at,
                    "updated_at": settings.updated_at
                }
            })
        finally:
            user_service.close()

    except Exception as e:
        print(f"[ERROR] Error getting user settings: {e}")
        return jsonify({"error": "Internal server error"}), 500


def update_user_settings():
    """Update user settings"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        print(f"[DEBUG] Updating settings for user: {user_id}")
        print(f"[DEBUG] Request data: {data}")

        user_service = UserService()
        user_service.connect()
        try:
            # Handle OpenAI API key update
            if 'openai_api_key' in data:
                api_key = data['openai_api_key']
                print(f"[DEBUG] Updating API key for user {user_id}")
                print(f"[DEBUG] API key length: {len(api_key) if api_key else 0}")
                print(f"[DEBUG] API key starts with sk-: {api_key.startswith('sk-') if api_key else False}")
                
                success, message = user_service.update_openai_api_key(user_id, api_key)
                print(f"[DEBUG] Update result: success={success}, message={message}")

                if success:
                    return jsonify({
                        "success": True,
                        "message": "OpenAI API key updated successfully"
                    })
                else:
                    return jsonify({"error": message}), 400

            return jsonify({"error": "No valid settings to update"}), 400

        finally:
            user_service.close()

    except Exception as e:
        print(f"[ERROR] Error updating user settings: {e}")
        return jsonify({"error": "Internal server error"}), 500


def get_api_usage_route():
    """Get current user's API usage statistics"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        security_service = get_openai_security_service()
        usage_stats = security_service.get_usage_stats(user_id)
        
        return jsonify({
            "success": True,
            "usage": usage_stats
        })

    except Exception as e:
        print(f"[ERROR] Error getting API usage: {e}")
        return jsonify({"error": "Internal server error"}), 500
