#!/usr/bin/env python3
"""
Script to create API keys for testing and development

This script demonstrates how to create API keys using your existing API key service.
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.services.api_key_service import APIKeyService


def create_api_key(
    user_id: str,
    name: str,
    permissions: list[str] | None = None,
    rate_limit_per_hour: int = 1000,
    expires_in_days: int | None = None,
):
    """
    Create a new API key using the API key service

    Args:
        user_id: ID of the user who will own this API key
        name: Human-readable name for the API key
        permissions: List of permissions for the key
        rate_limit_per_hour: Maximum requests per hour
        expires_in_days: Days until expiration (None for no expiration)
    """

    if permissions is None:
        # Default permissions for LLM agent access
        permissions = ["llm:chat", "llm:read"]

    print(f"Creating API key: {name}")
    print(f"User ID: {user_id}")
    print(f"Permissions: {permissions}")
    print(f"Rate Limit: {rate_limit_per_hour} requests/hour")
    if expires_in_days:
        print(f"Expires in: {expires_in_days} days")
    print("-" * 50)

    try:
        api_key_service = APIKeyService()
        success, message, api_key = api_key_service.create_api_key(
            user_id=user_id,
            name=name,
            permissions=permissions,
            rate_limit_per_hour=rate_limit_per_hour,
            expires_in_days=expires_in_days,
        )

        if success and api_key:
            print("✅ API key created successfully!")
            print(f"API Key: {api_key}")
            print(f"Message: {message}")
            print("\n🔑 **IMPORTANT: Save this API key now!**")
            print("It won't be shown again for security reasons.")

            return api_key
        else:
            print("❌ Failed to create API key")
            print(f"Error: {message}")
            return None

    except Exception as e:
        print(f"❌ Error creating API key: {e}")
        return None


def list_user_api_keys(user_id: str):
    """List all API keys for a specific user"""

    print(f"Listing API keys for user: {user_id}")
    print("-" * 50)

    try:
        api_key_service = APIKeyService()
        api_keys = api_key_service.get_api_keys_for_user(user_id)

        if api_keys:
            print(f"Found {len(api_keys)} API key(s):")
            for i, key in enumerate(api_keys, 1):
                print(f"\n{i}. {key.get('name', 'Unnamed')}")
                print(f"   ID: {key.get('id', 'Unknown')}")
                print(f"   Active: {key.get('is_active', False)}")
                print(f"   Permissions: {', '.join(key.get('permissions', []))}")
                print(f"   Rate Limit: {key.get('rate_limit_per_hour', 0)}/hour")
                print(f"   Created: {key.get('created_at', 'Unknown')}")
                if key.get("expires_at"):
                    print(f"   Expires: {key.get('expires_at')}")
        else:
            print("No API keys found for this user.")

    except Exception as e:
        print(f"❌ Error listing API keys: {e}")


def show_available_permissions():
    """Show all available permissions for API keys"""

    print("Available API Key Permissions:")
    print("-" * 50)

    # These are the permissions defined in your APIKey model
    permissions = [
        "patients:read",
        "patients:write",
        "patients:delete",
        "encounters:read",
        "encounters:write",
        "encounters:delete",
        "appointments:read",
        "appointments:write",
        "appointments:delete",
        "users:read",
        "users:write",
        "users:delete",
        "admin:read",
        "admin:write",
        "admin:delete",
    ]

    # Add some LLM-specific permissions that might be useful
    llm_permissions = [
        "llm:chat",  # Can use LLM chat functionality
        "llm:read",  # Can read chat history
        "llm:write",  # Can create new chats
        "llm:delete",  # Can delete chats
    ]

    print("Standard Permissions:")
    for perm in permissions:
        print(f"  • {perm}")

    print("\nLLM-Specific Permissions (recommended for testing):")
    for perm in llm_permissions:
        print(f"  • {perm}")

    print("\nNote: You can use any combination of these permissions.")


if __name__ == "__main__":
    print("🔑 API Key Creation Tool")
    print("=" * 50)

    if len(sys.argv) < 3:
        print(
            "Usage: python create_api_key.py <user_id> <key_name> [permissions] [rate_limit] [expires_days]"
        )
        print("\nExamples:")
        print("  python create_api_key.py user123 'LLM Testing'")
        print(
            "  python create_api_key.py user123 'Full Access' 'admin:read,admin:write' 5000 90"
        )
        print("\nAvailable commands:")
        print("  python create_api_key.py --permissions")
        print("  python create_api_key.py --list <user_id>")
        print()

        # Show available permissions
        show_available_permissions()
        sys.exit(1)

    command = sys.argv[1]

    if command == "--permissions":
        show_available_permissions()
        sys.exit(0)
    elif command == "--list":
        if len(sys.argv) < 3:
            print("Usage: python create_api_key.py --list <user_id>")
            sys.exit(1)
        user_id = sys.argv[2]
        list_user_api_keys(user_id)
        sys.exit(0)

    # Create API key
    user_id = sys.argv[1]
    key_name = sys.argv[2]

    # Parse optional parameters
    permissions = None
    rate_limit = 1000
    expires_days = None

    if len(sys.argv) > 3:
        permissions = sys.argv[3].split(",")

    if len(sys.argv) > 4:
        try:
            rate_limit = int(sys.argv[4])
        except ValueError:
            print(f"Invalid rate limit: {sys.argv[4]}")
            sys.exit(1)

    if len(sys.argv) > 5:
        try:
            expires_days = int(sys.argv[5])
        except ValueError:
            print(f"Invalid expiration days: {sys.argv[5]}")
            sys.exit(1)

    # Create the API key
    api_key = create_api_key(
        user_id=user_id,
        name=key_name,
        permissions=permissions,
        rate_limit_per_hour=rate_limit,
        expires_in_days=expires_days,
    )

    if api_key:
        print("\n🎉 API key created successfully!")
        print("\nNext steps:")
        print("1. Save the API key securely")
        print(
            "2. Test it with: python test_api_key_llm.py <url> <api_key> <openai_key>"
        )
        print("3. Use it in your applications with the X-API-Key header")
    else:
        print("\n❌ Failed to create API key. Check the error messages above.")
        sys.exit(1)
