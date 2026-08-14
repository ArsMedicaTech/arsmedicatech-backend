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
        draft_session_id: Optional[str] = None,
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
        :param draft_session_id: Optional temporary session ID for draft threads (used before care plan is created).
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
        self.draft_session_id = draft_session_id
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
        if self.draft_session_id is not None:
            result["draft_session_id"] = self.draft_session_id
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
            draft_session_id=data.get("draft_session_id"),
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
            DEFINE FIELD draft_session_id ON llm_chat_thread TYPE option<string>;
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


class LLMApiTrace:
    """
    Represents a single LLM API round-trip trace for observability.

    One pre-call row is written before the outbound OpenAI call, then MERGEd with
    response metadata after the call returns. Multiple rows can share the same
    trace_id (one per tool-call recursion / turn_index).
    """

    def __init__(
        self,
        trace_id: str,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        turn_index: int = 0,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        tool_names: Optional[List[str]] = None,
        tool_definitions_hash: Optional[str] = None,
        response_format: Optional[str] = None,
        request_timestamp: Optional[str] = None,
        finish_reason: Optional[str] = None,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
        id: Optional[str] = None,
    ) -> None:
        self.trace_id = trace_id
        self.thread_id = thread_id
        self.user_id = user_id
        self.turn_index = turn_index
        self.model = model
        self.messages = messages or []
        self.tool_names = tool_names
        self.tool_definitions_hash = tool_definitions_hash
        self.response_format = response_format
        self.request_timestamp = request_timestamp or datetime.now(timezone.utc).isoformat()
        self.finish_reason = finish_reason
        self.content = content
        self.tool_calls = tool_calls
        self.usage = usage
        self.duration_ms = duration_ms
        self.error = error
        self.id = id

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "trace_id": self.trace_id,
            "turn_index": self.turn_index,
            "request_timestamp": self.request_timestamp,
        }
        for key in (
            "thread_id",
            "user_id",
            "model",
            "messages",
            "tool_names",
            "tool_definitions_hash",
            "response_format",
            "finish_reason",
            "content",
            "tool_calls",
            "usage",
            "duration_ms",
            "error",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMApiTrace":
        trace_id = data.get("trace_id")
        if not trace_id:
            raise ValueError("trace_id is required and cannot be None")
        return cls(
            trace_id=trace_id,
            thread_id=data.get("thread_id"),
            user_id=data.get("user_id"),
            turn_index=data.get("turn_index", 0),
            model=data.get("model"),
            messages=data.get("messages"),
            tool_names=data.get("tool_names"),
            tool_definitions_hash=data.get("tool_definitions_hash"),
            response_format=data.get("response_format"),
            request_timestamp=data.get("request_timestamp"),
            finish_reason=data.get("finish_reason"),
            content=data.get("content"),
            tool_calls=data.get("tool_calls"),
            usage=data.get("usage"),
            duration_ms=data.get("duration_ms"),
            error=data.get("error"),
            id=data.get("id"),
        )

    @classmethod
    def schema(cls) -> str:
        return """
            DEFINE TABLE llm_api_trace SCHEMAFULL;
            DEFINE FIELD trace_id ON llm_api_trace TYPE string;
            DEFINE FIELD thread_id ON llm_api_trace TYPE option<record<llm_chat_thread>>;
            DEFINE FIELD user_id ON llm_api_trace TYPE option<record<user>>;
            DEFINE FIELD turn_index ON llm_api_trace TYPE int;
            DEFINE FIELD model ON llm_api_trace TYPE option<string>;
            DEFINE FIELD messages ON llm_api_trace TYPE option<array<object>>;
            DEFINE FIELD tool_names ON llm_api_trace TYPE option<array<string>>;
            DEFINE FIELD tool_definitions_hash ON llm_api_trace TYPE option<string>;
            DEFINE FIELD response_format ON llm_api_trace TYPE option<string>;
            DEFINE FIELD request_timestamp ON llm_api_trace TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD finish_reason ON llm_api_trace TYPE option<string>;
            DEFINE FIELD content ON llm_api_trace TYPE option<string>;
            DEFINE FIELD tool_calls ON llm_api_trace TYPE option<array<object>>;
            DEFINE FIELD usage ON llm_api_trace TYPE option<object>;
            DEFINE FIELD duration_ms ON llm_api_trace TYPE option<int>;
            DEFINE FIELD error ON llm_api_trace TYPE option<string>;
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
