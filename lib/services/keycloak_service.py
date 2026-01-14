"""
Keycloak Service for user registration via Admin API.
"""

import secrets
from typing import Any, Dict, Optional, Tuple

import requests

from settings import (
    KEYCLOAK_BASE_URL,
    KEYCLOAK_CLIENT_ID,
    KEYCLOAK_CLIENT_SECRET,
    KEYCLOAK_REALM,
    logger,
)


class KeycloakService:
    """
    Service for handling Keycloak user registration via Admin API.
    Uses the existing OAuth client credentials to obtain an admin token.
    """

    def __init__(self):
        self.base_url = KEYCLOAK_BASE_URL
        self.realm = KEYCLOAK_REALM
        self.client_id = KEYCLOAK_CLIENT_ID
        self.client_secret = KEYCLOAK_CLIENT_SECRET
        self._admin_token: Optional[str] = None

    def _get_admin_token(self) -> Optional[str]:
        """
        Get an admin access token for Keycloak Admin API using client credentials.

        IMPORTANT: For this to work, your Keycloak client must have:
        1. Service Accounts enabled (in Keycloak Admin Console: Clients > Your Client > Settings > Service Accounts Enabled = ON)
        2. Appropriate roles assigned (typically 'realm-admin' or 'manage-users' role)
           (In Keycloak Admin Console: Clients > Your Client > Service Account Roles > Client Roles > realm-management)

        :return: Admin access token or None if failed
        """
        if self._admin_token:
            return self._admin_token

        if not self.client_id or not self.client_secret:
            logger.error(
                "Keycloak client credentials not configured. "
                "KEYCLOAK_CLIENT_ID and KEYCLOAK_CLIENT_SECRET must be set."
            )
            return None

        try:
            # Use client credentials grant with the existing OAuth client
            token_url = (
                f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"
            )
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }

            response = requests.post(token_url, data=data, timeout=10)

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    f"Failed to get Keycloak admin token. Status: {response.status_code}, "
                    f"Response: {error_text}. "
                    f"Make sure your Keycloak client has Service Accounts enabled and appropriate roles assigned."
                )
                return None

            token_data = response.json()
            self._admin_token = token_data.get("access_token")
            if not self._admin_token:
                logger.error("Keycloak token response did not contain access_token")
                return None
            return self._admin_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get Keycloak admin token: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(
                    f"Response status: {e.response.status_code}, body: {e.response.text}"
                )
            return None

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        user_type: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Register a new user in Keycloak via Admin API.patient

        :param username: Username for the new user
        :param email: Email address for the new user
        :param password: Password for the new user
        :param first_name: First name of the user (optional)
        :param last_name: Last name of the user (optional)
        :param user_type: Type of user (e.g., 'admin', 'provider', 'patient') (optional - defaults to 'provider' if not specified)
        :return: Tuple (success: bool, user_id: Optional[str], error_message: Optional[str])
        """
        admin_token = self._get_admin_token()
        if not admin_token:
            return False, None, "Failed to obtain admin token"

        try:
            # Create user in Keycloak
            create_user_url = f"{self.base_url}/admin/realms/{self.realm}/users"
            headers = {
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json",
            }

            user_data: Dict[str, Any] = {
                "username": username,
                "email": email,
                "emailVerified": False,
                "enabled": True,
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            }

            if first_name:
                user_data["firstName"] = first_name
            if last_name:
                user_data["lastName"] = last_name

            if user_type:
                user_data["attributes"] = {"userType": [user_type]}
            else:
                user_data["attributes"] = {"userType": ["provider"]}

            response = requests.post(
                create_user_url, json=user_data, headers=headers, timeout=10
            )

            if response.status_code == 201:
                # User created successfully, get the user ID from the Location header
                location = response.headers.get("Location")
                if location:
                    # Extract user ID from location header
                    # Format: /admin/realms/{realm}/users/{user_id}
                    user_id = location.split("/")[-1]
                    logger.debug(f"Keycloak user created successfully: {user_id}")
                    return True, user_id, None
                else:
                    # If no location header, search for the user by username
                    user_id = self._get_user_id_by_username(username, admin_token)
                    if user_id:
                        return True, user_id, None
                    return False, None, "User created but could not retrieve user ID"
            elif response.status_code == 409:
                # User already exists
                error_msg = "User already exists in Keycloak"
                logger.warning(f"{error_msg}: {username}")
                return False, None, error_msg
            elif response.status_code == 403:
                # Forbidden - likely insufficient permissions
                error_msg = (
                    f"Permission denied when creating user in Keycloak. "
                    f"Make sure your Keycloak client has Service Accounts enabled and "
                    f"has been assigned the 'manage-users' or 'realm-admin' role. "
                    f"Response: {response.text}"
                )
                logger.error(error_msg)
                return False, None, error_msg
            else:
                error_msg = f"Failed to create user in Keycloak (Status {response.status_code}): {response.text}"
                logger.error(error_msg)
                return False, None, error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"Error registering user in Keycloak: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def _get_user_id_by_username(
        self, username: str, admin_token: str
    ) -> Optional[str]:
        """
        Get user ID by username from Keycloak.

        :param username: Username to search for
        :param admin_token: Admin access token
        :return: User ID or None if not found
        """
        try:
            search_url = f"{self.base_url}/admin/realms/{self.realm}/users"
            headers = {
                "Authorization": f"Bearer {admin_token}",
            }
            params = {"username": username, "exact": "true"}

            response = requests.get(
                search_url, headers=headers, params=params, timeout=10
            )
            response.raise_for_status()
            users = response.json()
            if users and len(users) > 0:
                return users[0].get("id")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching for user in Keycloak: {e}")
            return None

    def _generate_session_token(self) -> str:
        """
        Generate a secure session token for Keycloak users.

        :return: A secure random token string
        """
        return secrets.token_urlsafe(32)
