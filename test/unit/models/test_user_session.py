"""
Unit tests for the UserSession model.
"""

import pytest
from lib.models.user.user_session import UserSession


class TestUserSession:
    pytestmark = pytest.mark.unit

    def test_from_dict_preserves_persisted_session_token(self):
        persisted_token = "persisted-token-123"
        session = UserSession.from_dict(
            {
                "user_id": "user:1",
                "username": "testuser",
                "role": "provider",
                "session_token": persisted_token,
            }
        )
        assert session.session_token == persisted_token
