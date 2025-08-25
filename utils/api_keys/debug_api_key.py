#!/usr/bin/env python3
"""
Step-by-Step API Key Debug

This script checks each step of the API key creation and validation process
to identify where things are going wrong.
"""

import sys

# Add the project root to the Python path
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def step_1_check_database_connection():
    """Step 1: Check if we can connect to the database"""

    print("🔌 Step 1: Database Connection Test")
    print("=" * 50)

    try:
        from lib.services.api_key_service import APIKeyService

        api_key_service = APIKeyService()
        print("✅ APIKeyService imported successfully")

        # Try to connect
        api_key_service.connect()
        print("✅ Database connection successful")

        # Try a simple query to test
        result = api_key_service.db.query("SELECT count() FROM api_key")
        print(f"✅ Database query successful: {result}")

        api_key_service.close()
        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def step_2_list_existing_api_keys():
    """Step 2: List all existing API keys in the database"""

    print("\n🗄️  Step 2: List Existing API Keys")
    print("=" * 50)

    try:
        from lib.services.api_key_service import APIKeyService

        api_key_service = APIKeyService()
        api_key_service.connect()

        # Get all API keys
        query = "SELECT * FROM api_key"
        result = api_key_service.db.query(query)

        print(f"Raw database result: {result}")

        if result and len(result) > 0:
            # Extract API keys from result
            print("RESULT", result)
            api_keys_data = result
            print("API KEYS DATA", api_keys_data)

            if api_keys_data:
                print(f"✅ Found {len(api_keys_data)} API key(s) in database:")
                for i, key_data in enumerate(api_keys_data, 1):
                    print(f"\n{i}. Key Data:")
                    print(f"   ID: {key_data.get('id', 'Unknown')}")
                    print(f"   Name: {key_data.get('name', 'Unknown')}")
                    print(f"   User ID: {key_data.get('user_id', 'Unknown')}")
                    print(f"   Active: {key_data.get('is_active', 'Unknown')}")
                    print(f"   Permissions: {key_data.get('permissions', [])}")
                    print(f"   Created: {key_data.get('created_at', 'Unknown')}")
            else:
                print("⚠️  No API keys found in result data")
        else:
            print("⚠️  No API keys found in database")

        api_key_service.close()
        return True

    except Exception as e:
        print(f"❌ Failed to list API keys: {e}")
        return False


def step_3_create_test_api_key():
    """Step 3: Try to create a new API key"""

    print("\n🔑 Step 3: Create Test API Key")
    print("=" * 50)

    try:
        from lib.services.api_key_service import APIKeyService

        api_key_service = APIKeyService()
        api_key_service.connect()

        # Create a test API key
        user_id = "test_user_123"
        name = "Debug Test Key"
        permissions = ["admin:read"]
        rate_limit_per_hour = 1000
        expires_in_days = 30

        print("Creating API key with:")
        print(f"  User ID: {user_id}")
        print(f"  Name: {name}")
        print(f"  Permissions: {permissions}")
        print(f"  Rate Limit: {rate_limit_per_hour}/hour")
        print(f"  Expires in: {expires_in_days} days")

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

            # Store the key for testing
            with open("debug_api_key.txt", "w") as f:
                f.write(api_key)
            print("✅ API key saved to debug_api_key.txt")

            return api_key
        else:
            print(f"❌ Failed to create API key: {message}")
            return None

    except Exception as e:
        print(f"❌ Error creating API key: {e}")
        return False
    finally:
        if "api_key_service" in locals():
            api_key_service.close()


def step_4_validate_api_key(api_key: str):
    """Step 4: Test the API key validation"""

    print("\n✅ Step 4: Validate API Key")
    print("=" * 50)

    try:
        from lib.services.api_key_service import APIKeyService

        api_key_service = APIKeyService()
        api_key_service.connect()

        print(f"Testing validation for key: {api_key[:20]}...")

        is_valid, error, api_key_obj = api_key_service.validate_api_key(api_key)

        if is_valid and api_key_obj:
            print("✅ API key validation successful!")
            print(f"Key ID: {api_key_obj.id}")
            print(f"Name: {api_key_obj.name}")
            print(f"User ID: {api_key_obj.user_id}")
            print(f"Permissions: {api_key_obj.permissions}")
            print(f"Active: {api_key_obj.is_active}")
            print(f"Rate Limit: {api_key_obj.rate_limit_per_hour}/hour")

            if api_key_obj.is_expired():
                print("⚠️  WARNING: API key has expired!")

            return True
        else:
            print(f"❌ API key validation failed: {error}")
            return False

    except Exception as e:
        print(f"❌ Error validating API key: {e}")
        return False
    finally:
        if "api_key_service" in locals():
            api_key_service.close()


def step_5_test_rate_limit(api_key: str):
    """Step 5: Test rate limiting"""

    print("\n⏱️  Step 5: Test Rate Limiting")
    print("=" * 50)

    try:
        from lib.services.api_key_service import APIKeyService

        api_key_service = APIKeyService()
        api_key_service.connect()

        # First get the API key object
        is_valid, error, api_key_obj = api_key_service.validate_api_key(api_key)

        if not is_valid or not api_key_obj:
            print(f"❌ Cannot test rate limit - API key validation failed: {error}")
            return False

        # Test rate limit
        within_limit, rate_error = api_key_service.check_rate_limit(api_key_obj)

        if within_limit:
            print("✅ Rate limit check passed!")
            print(f"Rate limit: {api_key_obj.rate_limit_per_hour}/hour")
        else:
            print(f"⚠️  Rate limit exceeded: {rate_error}")

        return within_limit

    except Exception as e:
        print(f"❌ Error checking rate limit: {e}")
        return False
    finally:
        if "api_key_service" in locals():
            api_key_service.close()


def main():
    """Run all debug steps"""

    print("🔍 Step-by-Step API Key Debug")
    print("=" * 60)

    # Step 1: Check database connection
    db_ok = step_1_check_database_connection()
    if not db_ok:
        print("\n❌ Cannot continue - database connection failed")
        sys.exit(1)

    # Step 2: List existing keys
    step_2_list_existing_api_keys()

    # Step 3: Create test key
    api_key = step_3_create_test_api_key()
    if not api_key:
        print("\n❌ Cannot continue - API key creation failed")
        sys.exit(1)

    # Step 4: Validate the key
    validation_ok = step_4_validate_api_key(api_key)
    if not validation_ok:
        print("\n❌ Cannot continue - API key validation failed")
        sys.exit(1)

    # Step 5: Test rate limiting
    rate_limit_ok = step_5_test_rate_limit(api_key)

    # Summary
    print("\n📊 Debug Summary")
    print("=" * 50)
    print(f"Database Connection: {'✅ PASS' if db_ok else '❌ FAIL'}")
    print(f"API Key Creation: {'✅ PASS' if api_key else '❌ FAIL'}")
    print(f"API Key Validation: {'✅ PASS' if validation_ok else '❌ FAIL'}")
    print(f"Rate Limit Check: {'✅ PASS' if rate_limit_ok else '❌ FAIL'}")

    if api_key:
        print("\n🎯 **Next Steps:**")
        print(f"1. Your API key: {api_key}")
        print(
            f"2. Test with: python debug_api_key_auth.py {api_key} sk-your-openai-key"
        )
        print("3. Or test manually with the key above")

    print("\n💡 **If you're still getting 401 errors:**")
    print("   - Check that your Flask app has been restarted")
    print("   - Verify the API key is exactly as shown above")
    print("   - Check Flask logs for authentication details")

    return True
