"""
API Key Service for managing 3rd party API access
"""

import time
from datetime import datetime
from typing import Any, Dict, List

from lib.models.api_key import APIKey
from lib.models.common import OperationResult, Result, SurrealTableService
from lib.services.redis_client import get_redis_connection
from settings import logger


class APIKeyService(SurrealTableService[APIKey]):
    rate_limit_cache: Dict[str, Dict[str, Any]] = {}
    rate_limit_window = 3600  # 1 hour

    def validate_api_key(self, api_key: str) -> OperationResult[APIKey]:
        """
        Validate an API key and return the key object if valid

        :param api_key: The API key to validate
        :return: Tuple (is_valid: bool, error_message: str, api_key_obj: Optional[APIKey])
        """
        if not api_key:
            return OperationResult(False, "API key is required", None)

        try:
            self.connect()
            query = f"""
                SELECT * 
                FROM ONLY {self.model.table_name()}
                WHERE is_active=true and key_hash=$key_hash
            """

            params = {"key_hash": APIKey.hash_key(api_key)}
            result = self.db.query(query, params)

            if isinstance(result, str) or isinstance(result, list):
                return OperationResult(False, "No API keys found", None)

            api_key_obj = APIKey.model_validate(result)

            if api_key_obj.verify_key(api_key):
                if api_key_obj.is_expired():
                    return OperationResult(False, "API key has expired", None)

                api_key_obj.update_last_used()
                if api_key_obj.id and api_key_obj.last_used_at is not None:
                    self._update_last_used(
                        api_key_obj.id, last_used=api_key_obj.last_used_at
                    )
                return OperationResult(True, "API key is valid", api_key_obj)
            return OperationResult(False, "Invalid API key", None)

        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return OperationResult(False, f"Error validating API key: {str(e)}", None)
        finally:
            self.close()

    def _update_last_used(self, key_id: str, last_used: datetime) -> None:
        """
        Update the last used timestamp for an API key

        :param key_id: ID of the API key to update
        """
        try:
            result = self.get_by_id(key_id)
            if result.obj is None or result.obj.id is None:
                logger.error(f"Error updating API key last used: {result}")
                return

            partial_api_key = APIKey(id=result.obj.id, last_used_at=last_used)

            result = self.update(result.obj.id, partial_api_key)
            logger.info("Updating last used result: ", result)
        except Exception as e:
            logger.error(f"Error updating last used timestamp: {e}")

    def check_rate_limit(self, api_key_obj: APIKey) -> Result:
        """
        Check if the API key is within its rate limit

        :param api_key_obj: The API key object to check
        :return: Tuple (within_limit: bool, error_message: str)
        """
        try:
            redis = get_redis_connection()
            key = f"api_key_rate_limit:{api_key_obj.id}"
            current_time = time.time()

            # Get current usage count
            usage_data = redis.get(key)
            if usage_data:
                usage = eval(usage_data)  # type: ignore
                if current_time - usage["window_start"] < self.rate_limit_window:
                    if usage["count"] >= api_key_obj.rate_limit_per_hour:
                        return Result(
                            False,
                            f"Rate limit exceeded. Maximum {api_key_obj.rate_limit_per_hour} requests per hour.",
                        )
                else:
                    # Reset window
                    usage: Dict[str, float] = {"count": 0, "window_start": current_time}
            else:
                usage: Dict[str, float] = {"count": 0, "window_start": current_time}

            # Increment count
            usage["count"] += 1

            # Store updated usage
            redis.setex(key, self.rate_limit_window, str(usage))

            return Result(True, "")

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return Result(False, f"Error checking rate limit: {str(e)}")

    def get_api_keys_for_user(self, user_id: str) -> List[APIKey]:
        """
        Get all API keys for a specific user

        :param user_id: ID of the user
        :return: List of API key dictionaries (without the actual key)
        """
        try:
            self.connect()
            query = "SELECT * FROM api_key WHERE user_id = $user_id ORDER BY created_at DESC"
            params = {"user_id": user_id}

            result = self.db.query(query, params)

            if isinstance(result, dict) or isinstance(result, str):
                return []

            api_keys: List[APIKey] = []

            for key_data in result:
                key_data.pop("key_hash", None)
                api_key_obj = APIKey.model_validate(key_data)
                api_key_obj.id = str(key_data["id"])
                # TODO: move this to route level
                # Don't include the actual key hash in the response
                api_keys.append(api_key_obj)
            return api_keys

        except Exception as e:
            logger.error(f"Error getting API keys for user: {e}")
            return []
        finally:
            self.close()

    def deactivate_api_key(self, key_id: str, user_id: str) -> Result:
        """
        Deactivate an API key (soft delete)

        :param key_id: ID of the API key to deactivate
        :param user_id: ID of the user (for authorization)
        :return: Tuple (success: bool, message: str)
        """
        try:
            self.connect()
            result = self.update(key_id, APIKey(is_active=False))

            if result and isinstance(result, dict):
                logger.info(f"Deactivated API key {key_id} for user {user_id}")
                return Result(True, "API key deactivated successfully")
            else:
                return Result(False, "API key not found or access denied")

        except Exception as e:
            logger.error(f"Error deactivating API key: {e}")
            return Result(False, f"Error deactivating API key: {str(e)}")
        finally:
            self.close()

    def get_usage_stats(self, api_key_obj: APIKey) -> Dict[str, Any]:
        """
        Get usage statistics for an API key

        :param api_key_obj: The API key object
        :return: Dictionary with usage statistics
        """
        try:
            redis = get_redis_connection()
            key = f"api_key_rate_limit:{api_key_obj.id}"

            usage_data = redis.get(key)
            if usage_data:
                usage = eval(usage_data)  # type: ignore
                current_time = time.time()

                if current_time - usage["window_start"] < self.rate_limit_window:
                    return {
                        "requests_this_hour": usage["count"],
                        "rate_limit": api_key_obj.rate_limit_per_hour,
                        "remaining_requests": max(
                            0, api_key_obj.rate_limit_per_hour - usage["count"]
                        ),
                        "window_resets_in": int(
                            self.rate_limit_window
                            - (current_time - usage["window_start"])
                        ),
                    }

            return {
                "requests_this_hour": 0,
                "rate_limit": api_key_obj.rate_limit_per_hour,
                "remaining_requests": api_key_obj.rate_limit_per_hour,
                "window_resets_in": 0,
            }

        except Exception as e:
            logger.error(f"Error getting usage stats: {e}\nobject:{api_key_obj}")
            raise e


# class APIKeyService(Service[APIKey]):
#     """
#     Service for managing API keys, including creation, validation, rate limiting, and usage tracking
#     """

#     def __init__(self) -> None:
#         """
#         Initialize the API key service
#         """
#         self.db = DbController()
#         self.logger = logger
#         self.debug = DEBUG
#         self.model = APIKey
#         self.rate_limit_cache: Dict[str, Dict[str, Any]] = {}
#         self.rate_limit_window = 3600  # 1 hour

#     def create(self, obj: APIKey) -> OperationResult[APIKey]:
#         """
#         Create a new API key

#         :param user_id: ID of the user creating the key
#         :param name: Human-readable name for the key
#         :param permissions: List of permissions for the key
#         :param rate_limit_per_hour: Maximum requests per hour
#         :param expires_in_days: Days until expiration (None for no expiration)
#         :return: Tuple (success: bool, message: str, api_key: Optional[str])
#         """
#         try:
#             self.connect()
#             result = self.db.create(self.model.table_name, obj.to_dict())
#             hash: str
#             salt: str
#             hash, salt = itemgetter("hash", "salt")(APIKey.generate_hash_key(api_key))
#             if isinstance(result, dict) and result["id"]:
#                 # Extract the created record ID
#                 api_key_obj = APIKey.from_dict(result)
#                 api_key_obj.id = str(result["id"])
#                 logger.info(
#                     f"Created API key '{api_key_obj.name}' for user {api_key_obj.user_id}"
#                 )
#                 return OperationResult(
#                     True, "API key created successfully", api_key_obj
#                 )
#             elif "already exists" in result:
#                 logger.warning(
#                     f"API key '{obj.name}' for user {obj.user_id} already exists"
#                 )
#                 return OperationResult(False, "API key already exists", None)
#             else:
#                 return OperationResult(False, "Failed to create API key", None)
#         except Exception as e:
#             logger.error(f"Error creating API key: {e}")
#             return OperationResult(False, f"Error creating API key: {str(e)}", None)
#         finally:
#             self.close()

#     def update(self, id: str, obj: APIKey) -> OperationResult[APIKey]:
#         try:
#             to_update = obj.to_dict()
#             to_update.pop("id")
#             query = "UPDATE ONLY api_key CONTENT $content WHERE id = $key_id"
#             params: Dict[str, Any] = {
#                 "key_id": id,
#                 "content": to_update,
#             }
#             result = self.db.query(query, params)

#             if isinstance(result, dict) and result["id"]:
#                 api_key_obj = APIKey.from_dict(result)
#                 api_key_obj.id = str(result["id"])
#                 logger.info(
#                     f"Updated API key '{api_key_obj.name}' for user {api_key_obj.user_id}"
#                 )
#                 return OperationResult(True, "Successfully updated", api_key_obj)
#             else:
#                 return OperationResult(False, "Failed to create API key", None)

#         except Exception as e:
#             logger.error(f"Error updating last used timestamp: {e}")
#             return OperationResult(False, "Failed to update api key", None)

#     # TODO: User authentication shouldn't belong on this level. probably rename these from service
#     # to something else, and have service belong to the user space level
#     def delete(self, id: str) -> OperationResult[APIKey]:
#         """
#         Delete an API key

#         :param key_id: ID of the API key to delete
#         :return: Tuple (success: bool, message: str)
#         """
#         try:
#             self.connect()
#             params = {"key_id": id}

#             query = "SELECT * FROM ONLY api_key WHERE id = $key_id"
#             result = self.db.query(query, params)
#             if not isinstance(result, dict):
#                 return OperationResult(False, "API key not found.", None)

#             delete_query = "DELETE FROM api_key WHERE id = $key_id"
#             delete_result = self.db.query(delete_query, params)

#             if delete_result and len(delete_result) > 0:
#                 logger.info(f"Deleted API key {id}.")
#                 return OperationResult(True, "API key deleted successfully", None)
#             else:
#                 return OperationResult(False, "Failed to delete API key", None)
#         except Exception as e:
#             logger.error(f"Error deleting API key: {e}")
#             return OperationResult(False, f"Error deleting API key: {str(e)}", None)
#         finally:
#             self.close()

#     def get_by_id(self, id: str) -> OperationResult[APIKey]:
#         try:
#             self.connect()
#             params = {"key_id": id}

#             query = "SELECT * FROM ONLY api_key WHERE id = $key_id"
#             result = self.db.query(query, params)

#             if isinstance(result, dict):
#                 api_key_obj = APIKey.from_dict(result)
#                 api_key_obj.id = str(result["id"])
#                 return OperationResult(True, "got API key successfully", api_key_obj)
#             else:
#                 logger.error(f"Failed to query for api_key {id}.")
#                 return OperationResult(False, "API key not found.", None)
#         except Exception as e:
#             logger.error(f"Error getting API key: {e}")
#             return OperationResult(False, f"Error getting API key: {str(e)}", None)
#         finally:
#             self.close()

#     def get_all(self) -> OperationResult[List[APIKey]]:
#         try:
#             self.connect()
#             result = self.db.select_many(Table("api_key"))

#             if isinstance(result, list):
#                 parsed_keys: List[APIKey] = []
#                 for api_key in result:
#                     api_key_obj = APIKey.from_dict(api_key)
#                     api_key_obj.id = str(api_key["id"])
#                     parsed_keys.append(api_key_obj)
#                 return OperationResult(
#                     True, "got all API keys successfully", parsed_keys
#                 )
#             else:
#                 logger.error("Failed to query for api_keys.")
#                 return OperationResult(False, "Failed to query for api keys.", None)
#         except Exception as e:
#             logger.error(f"Error getting all API keys: {e}")
#             return OperationResult(False, f"Error getting all API keys: {str(e)}", None)
#         finally:
#             self.close()
