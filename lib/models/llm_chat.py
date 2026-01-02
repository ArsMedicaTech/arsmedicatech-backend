"""
LLM Chat Models
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.data_types import UserID


class LLMChatThread:
    """
    Represents a chat thread/conversation with an LLM assistant.
    Contains metadata about the conversation context.
    """

    def __init__(
        self,
        user_id: UserID,
        assistant_id: str = "ai-assistant",
        patient_id: Optional[str] = None,
        care_plan_id: Optional[str] = None,
        title: Optional[str] = None,
        system_prompt_version: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        id: Optional[str] = None,
    ) -> None:
        """
        Initializes an LLMChatThread instance.
        :param user_id: User ID of the chat participant.
        :param assistant_id: ID of the assistant (default is "ai-assistant").
        :param patient_id: Optional patient ID associated with this thread.
        :param care_plan_id: Optional care plan ID associated with this thread.
        :param title: Optional title for the thread.
        :param system_prompt_version: Optional system prompt version for AI agent configuration.
        :param created_at: Creation timestamp of the thread in ISO format. If not provided, the current time is used.
        :param updated_at: Last update timestamp of the thread in ISO format. If not provided, the current time is used.
        :param id: Optional unique identifier for the thread. If not provided, it will be generated.
        :return: None
        """
        self.user_id = user_id
        self.assistant_id = assistant_id
        self.patient_id = patient_id
        self.care_plan_id = care_plan_id
        self.title = title
        self.system_prompt_version = system_prompt_version
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()
        self.id = id

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the LLMChatThread instance to a dictionary representation.
        :return: Dict containing the thread details.
        """
        result: Dict[str, Any] = {
            "user_id": self.user_id,
            "assistant_id": self.assistant_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.patient_id is not None:
            result["patient_id"] = self.patient_id
        if self.care_plan_id is not None:
            result["care_plan_id"] = self.care_plan_id
        if self.title is not None:
            result["title"] = self.title
        if self.system_prompt_version is not None:
            result["system_prompt_version"] = self.system_prompt_version
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMChatThread":
        """
        Creates an LLMChatThread instance from a dictionary.
        :param data: Dictionary containing thread details.
        :return: LLMChatThread instance
        """
        thread_id = data.get("id")
        if hasattr(thread_id, "__str__"):
            thread_id = str(thread_id)
        user_id = data.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required and cannot be None")
        return cls(
            user_id=user_id,
            assistant_id=data.get("assistant_id", "ai-assistant"),
            patient_id=data.get("patient_id"),
            care_plan_id=data.get("care_plan_id"),
            title=data.get("title"),
            system_prompt_version=data.get("system_prompt_version"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            id=thread_id,
        )

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the llm_chat_thread table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE llm_chat_thread SCHEMAFULL;
            DEFINE FIELD user_id ON llm_chat_thread TYPE record<user>;
            DEFINE FIELD assistant_id ON llm_chat_thread TYPE string;
            DEFINE FIELD patient_id ON llm_chat_thread TYPE option<record<patient>>;
            DEFINE FIELD care_plan_id ON llm_chat_thread TYPE option<string>;
            DEFINE FIELD title ON llm_chat_thread TYPE option<string>;
            DEFINE FIELD system_prompt_version ON llm_chat_thread TYPE option<string>;
            DEFINE FIELD created_at ON llm_chat_thread TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON llm_chat_thread TYPE datetime VALUE time::now();
        """


class LLMChatMessage:
    """
    Represents a single message within a chat thread.
    """

    def __init__(
        self,
        thread_id: str,
        role: str,
        content: str,
        used_tools: Optional[List[str]] = None,
        created_at: Optional[str] = None,
        id: Optional[str] = None,
    ) -> None:
        """
        Initializes an LLMChatMessage instance.
        :param thread_id: ID of the chat thread this message belongs to.
        :param role: Role of the message sender ('user' or 'assistant').
        :param content: The text content of the message.
        :param used_tools: Optional list of tools used in this message.
        :param created_at: Creation timestamp of the message in ISO format. If not provided, the current time is used.
        :param id: Optional unique identifier for the message. If not provided, it will be generated.
        :return: None
        """
        self.thread_id = thread_id
        self.role = role
        self.content = content
        self.used_tools = used_tools or []
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.id = id

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the LLMChatMessage instance to a dictionary representation.
        :return: Dict containing the message details.
        """
        result: Dict[str, Any] = {
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }
        if self.used_tools:
            result["used_tools"] = self.used_tools
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMChatMessage":
        """
        Creates an LLMChatMessage instance from a dictionary.
        :param data: Dictionary containing message details.
        :return: LLMChatMessage instance
        """
        message_id = data.get("id")
        if hasattr(message_id, "__str__"):
            message_id = str(message_id)
        thread_id = data.get("thread_id")
        if thread_id is None:
            raise ValueError("thread_id is required and cannot be None")
        return cls(
            thread_id=thread_id,
            role=data.get("role", "user"),
            content=data.get("content", ""),
            used_tools=data.get("used_tools", []),
            created_at=data.get("created_at"),
            id=message_id,
        )

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the llm_chat_message table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE llm_chat_message SCHEMAFULL;
            DEFINE FIELD thread_id ON llm_chat_message TYPE record<llm_chat_thread>;
            DEFINE FIELD role ON llm_chat_message TYPE string;
            DEFINE FIELD content ON llm_chat_message TYPE string;
            DEFINE FIELD used_tools ON llm_chat_message TYPE option<array<string>>;
            DEFINE FIELD created_at ON llm_chat_message TYPE datetime VALUE time::now() READONLY;
        """


# Legacy LLMChat class - kept for backward compatibility during migration
class LLMChat:
    """
    Represents a chat session with an LLM (Large Language Model) assistant.
    DEPRECATED: This class is kept for backward compatibility. Use LLMChatThread and LLMChatMessage instead.
    """

    def __init__(
        self,
        user_id: UserID,
        assistant_id: str = "ai-assistant",
        messages: Optional[List[Dict[str, Any]]] = None,
        created_at: Optional[str] = None,
        id: Optional[str] = None,
    ) -> None:
        """
        Initializes an LLMChat instance.
        :param user_id: User ID of the chat participant.
        :param assistant_id: ID of the assistant (default is "ai-assistant").
        :param messages: List of messages in the chat. Each message should be a dictionary with keys like 'sender', 'text', and 'timestamp'.
        :param created_at: Creation timestamp of the chat session in ISO format. If not provided, the current time is used.
        :param id: Optional unique identifier for the chat session. If not provided, it will be generated.
        :return: None
        """
        self.user_id = user_id
        self.assistant_id = assistant_id
        self.messages = messages or []
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.id = id

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the LLMChat instance to a dictionary representation.
        :return: Dict containing the chat details.
        """
        return {
            "user_id": self.user_id,
            "assistant_id": self.assistant_id,
            "messages": self.messages,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMChat":
        """
        Creates an LLMChat instance from a dictionary.
        :param data: Dictionary containing chat details. Expected keys are 'user_id', 'assistant_id', 'messages', 'created_at', and 'id'.
        :return: LLMChat instance
        """
        chat_id = data.get("id")
        if hasattr(chat_id, "__str__"):
            chat_id = str(chat_id)
        user_id = data.get("user_id")
        if user_id is None:
            raise ValueError("user_id is required and cannot be None")
        return cls(
            user_id=user_id,
            assistant_id=data.get("assistant_id", "ai-assistant"),
            messages=data.get("messages", []),
            created_at=data.get("created_at"),
            id=chat_id,
        )

    def add_message(
        self, sender: str, text: str, used_tools: Optional[List[str]] = None
    ) -> None:
        """
        Adds a new message to the chat session.
        :param sender: The sender of the message (e.g., 'user' or 'assistant').
        :param text: The text content of the message.
        :param used_tools: Optional list of tools used in this message.
        :return: None
        """
        message: Dict[str, Any] = {
            "sender": sender,
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if used_tools:
            message["usedTools"] = used_tools
        self.messages.append(message)

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the llm chat table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE llm_chat SCHEMAFULL;
            DEFINE FIELD user_id ON llm_chat TYPE record<user>;
            DEFINE FIELD assistant_id ON llm_chat TYPE string;
            DEFINE FIELD messages ON llm_chat TYPE array<object>;
            DEFINE FIELD created_at ON llm_chat TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON llm_chat TYPE datetime VALUE time::now();
        """
