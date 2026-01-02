"""
LLM Chat Service
"""

from typing import Any, Dict, List, Optional

from amt_nano.db.surreal import DbController

from lib.data_types import UserID
from lib.models.llm_chat import LLMChat, LLMChatMessage, LLMChatThread
from settings import logger


class LLMChatService:
    """
    Service for managing LLM chats using the thread/message pattern.
    Supports both the new thread-based approach and legacy chat retrieval.
    """

    def __init__(self, db_controller: Optional[DbController] = None) -> None:
        """
        Initialize the LLMChatService with a database controller.
        :param db_controller: Optional[DbController] - The database controller to use. If None, a new DbController instance is created.
        :return: None
        """
        self.db = db_controller or DbController()

    def connect(self) -> None:
        """
        Connect to the database.
        :return: None
        """
        try:
            self.db.connect()
        except Exception as e:
            logger.error(f"Error connecting to the database: {e}")
            raise

    def close(self) -> None:
        """
        Close the database connection.
        :return: None
        """
        self.db.close()

    def get_or_create_thread(
        self,
        user_id: UserID,
        assistant_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Finds a thread matching the specific context, or creates one.

        :param user_id: UserID - The ID of the user.
        :param assistant_id: str - The ID of the assistant.
        :param context: Optional dict containing 'patient_id' and/or 'care_plan_id'.
        :return: str - The thread ID (e.g., 'llm_chat_thread:zk98...').
        """
        context = context or {}
        patient_id = context.get("patient_id")
        care_plan_id = context.get("care_plan_id")

        # Build query to find existing thread
        query_parts = [
            "SELECT * FROM llm_chat_thread",
            "WHERE user_id = $user_id",
            "AND assistant_id = $assistant_id",
        ]
        params: Dict[str, Any] = {
            "user_id": user_id,
            "assistant_id": assistant_id,
        }

        # Add context filters if provided
        if patient_id:
            query_parts.append("AND patient_id = $patient_id")
            params["patient_id"] = patient_id
        else:
            query_parts.append("AND patient_id IS NONE")

        if care_plan_id:
            query_parts.append("AND care_plan_id = $care_plan_id")
            params["care_plan_id"] = care_plan_id
        else:
            query_parts.append("AND care_plan_id IS NONE")

        query_parts.append("LIMIT 1")
        query = " ".join(query_parts)

        result = self.db.query(query, params)
        if result and isinstance(result, list) and len(result) > 0:
            thread_data = result[0]
            thread_id = thread_data.get("id")
            if thread_id:
                # Extract ID if it's a full record reference
                if isinstance(thread_id, str) and ":" in thread_id:
                    return thread_id
                elif isinstance(thread_id, dict) and "id" in thread_id:
                    return str(thread_id["id"])
                return str(thread_id)

        # Create new thread if not found
        thread = LLMChatThread(
            user_id=user_id,
            assistant_id=assistant_id,
            patient_id=patient_id,
            care_plan_id=care_plan_id,
            title=context.get("title"),
            system_prompt_version=context.get("system_prompt_version"),
        )
        result = self.db.create("llm_chat_thread", thread.to_dict())
        if result and isinstance(result, dict):
            thread_id = result.get("id")
            if thread_id:
                return str(thread_id)
        raise ValueError("Failed to create thread")

    def get_thread(self, thread_id: str) -> Optional[LLMChatThread]:
        """
        Get a specific thread by ID.

        :param thread_id: str - The thread ID (can be full format like 'llm_chat_thread:xyz' or just 'xyz').
        :return: Optional[LLMChatThread] - The thread if found, otherwise None.
        """
        # Handle both full record format and just the ID
        if ":" not in thread_id:
            record_id = f"llm_chat_thread:{thread_id}"
        else:
            record_id = thread_id

        # Use direct record retrieval (SurrealDB doesn't support parameterized record IDs)
        result = self.db.query(f"SELECT * FROM {record_id}")
        if result and isinstance(result, list) and len(result) > 0:
            return LLMChatThread.from_dict(result[0])
        return None

    def get_threads_for_user(
        self, user_id: UserID, assistant_id: Optional[str] = None
    ) -> List[LLMChatThread]:
        """
        Get all threads for a user, optionally filtered by assistant_id.

        :param user_id: UserID - The ID of the user.
        :param assistant_id: Optional[str] - Filter by assistant ID.
        :return: List[LLMChatThread] - List of threads for the user.
        """
        if assistant_id:
            query = "SELECT * FROM llm_chat_thread WHERE user_id = $user_id AND assistant_id = $assistant_id ORDER BY updated_at DESC"
            params = {"user_id": user_id, "assistant_id": assistant_id}
        else:
            query = "SELECT * FROM llm_chat_thread WHERE user_id = $user_id ORDER BY updated_at DESC"
            params = {"user_id": user_id}

        result = self.db.query(query, params)
        threads = []
        if result and isinstance(result, list):
            for thread_data in result:
                if isinstance(thread_data, dict):
                    threads.append(LLMChatThread.from_dict(thread_data))
        return threads

    def get_thread_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Fetches messages for a specific thread, ordered by creation time.
        Returns messages in a format compatible with the LLM agent.

        :param thread_id: str - The thread ID (can be full format like 'llm_chat_thread:xyz' or just 'xyz').
        :return: List[Dict] - List of message dictionaries with 'role' and 'content' keys.
        """
        # Handle both full record format and just the ID
        if ":" not in thread_id:
            record_id = f"llm_chat_thread:{thread_id}"
        else:
            record_id = thread_id

        query = """
        SELECT * FROM llm_chat_message 
        WHERE thread_id = $thread_id 
        ORDER BY created_at ASC
        """
        result = self.db.query(query, {"thread_id": record_id})

        messages = []
        if result and isinstance(result, list):
            for msg_data in result:
                if isinstance(msg_data, dict):
                    # Convert to format expected by LLM agent
                    messages.append(
                        {
                            "role": msg_data.get("role", "user"),
                            "content": msg_data.get("content", ""),
                        }
                    )
        return messages

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        used_tools: Optional[List[str]] = None,
    ) -> LLMChatMessage:
        """
        Inserts a new message record for a thread.
        This is an atomic INSERT operation, not an UPDATE.

        :param thread_id: str - The thread ID this message belongs to (can be full format like 'llm_chat_thread:xyz' or just 'xyz').
        :param role: str - The role of the message sender ('user' or 'assistant').
        :param content: str - The content of the message.
        :param used_tools: Optional list of tools used in this message.
        :return: LLMChatMessage - The created message object.
        """
        # Handle both full record format and just the ID
        if ":" not in thread_id:
            record_id = f"llm_chat_thread:{thread_id}"
        else:
            record_id = thread_id

        message = LLMChatMessage(
            thread_id=record_id,
            role=role,
            content=content,
            used_tools=used_tools,
        )

        # Insert the message (atomic operation)
        result = self.db.create("llm_chat_message", message.to_dict())
        if result and isinstance(result, dict):
            message_id = result.get("id")
            if message_id:
                message.id = str(message_id)

        # Update thread's updated_at timestamp
        try:
            # Use direct record update (SurrealDB doesn't support parameterized record IDs in UPDATE)
            update_query = f"UPDATE {record_id} SET updated_at = time::now()"
            self.db.query(update_query)
        except Exception as e:
            logger.warning(f"Failed to update thread timestamp: {e}")

        return message

    # Legacy methods for backward compatibility
    def get_llm_chats_for_user(self, user_id: UserID) -> List[LLMChat]:
        """
        Get all LLM chats for a user (legacy method).
        DEPRECATED: Use get_threads_for_user instead.

        :param user_id: UserID - The ID of the user for whom to retrieve chats.
        :return: List[LLMChat] - A list of LLMChat objects for the specified user.
        """
        result = self.db.query(
            "SELECT * FROM llm_chat WHERE user_id = $user_id", {"user_id": user_id}
        )
        chats = []
        if result and isinstance(result, list):
            for chat_data in result:
                if isinstance(chat_data, dict):
                    chats.append(LLMChat.from_dict(chat_data))
        return chats

    def get_llm_chat(self, user_id: UserID, assistant_id: str) -> Optional[LLMChat]:
        """
        Get a specific LLM chat for a user and assistant (legacy method).
        DEPRECATED: Use get_thread instead.

        :param user_id: UserID - The ID of the user.
        :param assistant_id: str - The ID of the assistant.
        :return: Optional[LLMChat] - The LLMChat object if found, otherwise None.
        """
        result = self.db.query(
            "SELECT * FROM llm_chat WHERE user_id = $user_id AND assistant_id = $assistant_id",
            {"user_id": user_id, "assistant_id": assistant_id},
        )
        if result and isinstance(result, list) and len(result) > 0:
            return LLMChat.from_dict(result[0])
        return None

    def create_llm_chat(self, user_id: UserID, assistant_id: str) -> LLMChat:
        """
        Create a new LLM chat for a user and assistant (legacy method).
        DEPRECATED: Use get_or_create_thread instead.

        :param user_id: UserID - The ID of the user.
        :param assistant_id: str - The ID of the assistant.
        :return: LLMChat - The newly created LLMChat object.
        """
        chat = LLMChat(user_id=user_id, assistant_id=assistant_id)
        result = self.db.create("llm_chat", chat.to_dict())
        if result and isinstance(result, dict):
            chat.id = result.get("id")
        return chat
