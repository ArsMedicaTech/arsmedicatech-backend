"""
LLM Agent Endpoint
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, cast

from flask import Response, jsonify, request

from lib.data_types import UserID
from lib.llm.agent import DEFAULT_SYSTEM_PROMPT, LLMAgent, LLMModel, ToolDefinition
from lib.llm.v2.hierarchical_agent import HierarchicalAgentManager
from lib.services.auth_decorators import get_current_user
from lib.services.llm_chat_service import LLMChatService
from lib.services.openai_security import get_openai_security_service
from settings import AGENT_VERSION, MCP_URL, logger, mcp_config


async def _get_agent_response(
    mcp_conf: Dict[str, Any],
    api_key: str,
    prompt: str,
    history: List[Dict[str, Any]],
    response_format: Any,
    **kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handles the entire async workflow for getting a response from the LLM agent.
    """
    manager = HierarchicalAgentManager(mcp_conf)

    async with manager:
        system_prompt_val = kwargs.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        system_prompt: str = (
            system_prompt_val
            if isinstance(system_prompt_val, str)
            else DEFAULT_SYSTEM_PROMPT
        )

        agent = LLMAgent(
            mcp_config=dict(cast(Dict[str, Any], mcp_config)),
            api_key=api_key,
            model=LLMModel.GPT_5_NANO,
            system_prompt=system_prompt,
        )

        # 3) Wire the manager's discovered tools into the agent
        agent.tool_definitions = cast(List[ToolDefinition], manager.openai_defs)
        agent.tool_func_dict = manager.func_lookup

        # 4) Set the conversation history from the database
        # Convert LLMChat message format to LLMAgent format
        converted_history = []
        for msg in history:
            if isinstance(msg, dict):
                # Convert sender to role and text to content
                role = msg.get("sender")
                content = msg.get("text", "")

                # Map sender values to expected role values
                if role == "Me":
                    role = "user"
                elif role == "AI Assistant":
                    role = "assistant"
                elif role is None:
                    # Skip messages with None sender
                    continue

                converted_history.append({"role": role, "content": content})

        agent.message_history = converted_history

        # 3. Get the completion from the agent
        response = await agent.complete(
            prompt,
            response_format=response_format,
        )
        return response


def llm_agent_endpoint_route() -> Tuple[Response, int]:
    """
    Route for the LLM agent endpoint.
    Supports both session-based authentication and API key authentication.
    :return: Response object with JSON data or error message.
    """
    logger.debug("[DEBUG] /api/llm_chat called")
    logger.debug("[DEBUG] Request headers: %s", str(dict(request.headers)))

    # Get current user from auth decorator (either session or API key)
    current_user = get_current_user()
    if not current_user:
        logger.debug("[DEBUG] Not authenticated in /api/llm_chat")
        return jsonify({"error": "Not authenticated"}), 401

    current_user_id = current_user.user_id
    logger.debug("[DEBUG] User authenticated: %s", current_user_id)

    llm_chat_service = LLMChatService()
    llm_chat_service.connect()
    try:
        if request.method == "GET":
            chats = llm_chat_service.get_llm_chats_for_user(UserID(current_user_id))
            return jsonify([chat.to_dict() for chat in chats]), 200
        elif request.method == "POST":
            data: Optional[Dict[str, Any]] = request.json
            if data is None:
                return jsonify({"error": "Invalid JSON data"}), 400

            assistant_id = data.get("assistant_id", "ai-assistant")
            prompt = data.get("prompt")
            if not prompt:
                return jsonify({"error": "No prompt provided"}), 400

            # Check if OpenAI API key is provided in request (for programmatic access)
            openai_api_key = data.get("openai_api_key")

            if not openai_api_key:
                # Fall back to getting user's stored OpenAI API key with security validation
                security_service = get_openai_security_service()
                openai_api_key, error = (
                    security_service.get_user_api_key_with_validation(
                        str(current_user_id)
                    )
                )

                if not openai_api_key:
                    return jsonify({"error": error}), 400
            else:
                # Validate the provided OpenAI API key format (basic check)
                if not openai_api_key.startswith("sk-"):
                    return jsonify({"error": "Invalid OpenAI API key format"}), 400

                logger.debug("[DEBUG] Using OpenAI API key from request body")

            # Add user message to persistent chat
            chat = llm_chat_service.add_message(
                UserID(current_user_id), assistant_id, "Me", prompt
            )

            response_format = data.get("response_format")  # type: ignore

            # Use the persistent chat history as context
            history: list[Dict[str, Any]] = chat.messages
            logger.debug(f"History: {history}")

            agent_mcp_config = (
                dict(cast(Dict[str, Any], mcp_config))
                if AGENT_VERSION == "v2"
                else {"url": MCP_URL}  # Adapt based on your config structure
            )

            if AGENT_VERSION:
                # raise NotImplementedError("LLM Agent v2 is not yet implemented")
                # agent = asyncio.run(
                #     LLMAgent.from_mcp_config(
                #         mcp_config=dict(cast(Dict[str, Any], mcp_config)),
                #         api_key=openai_api_key,
                #         model=LLMModel.GPT_5_NANO,
                #     )
                # )
                response = asyncio.run(
                    _get_agent_response(
                        mcp_conf=agent_mcp_config,
                        api_key=openai_api_key,
                        prompt=prompt,
                        history=history,
                        response_format=response_format,
                    )
                )
            else:
                agent = asyncio.run(
                    LLMAgent.from_mcp(
                        mcp_url=MCP_URL,
                        api_key=openai_api_key,
                        model=LLMModel.GPT_5_NANO,
                    )
                )

                response = asyncio.run(
                    agent.complete(prompt, response_format=response_format)
                )

            logger.debug("response", type(response), response)

            # Log API usage (only if using stored key, not if provided in request)
            if not data.get("openai_api_key"):
                security_service = get_openai_security_service()
                security_service.log_api_usage(
                    str(current_user_id), str(LLMModel.GPT_5_NANO)
                )

            # Add assistant response to persistent chat
            used_tools = response.get("used_tools", [])
            chat = llm_chat_service.add_message(
                UserID(current_user_id),
                assistant_id,
                "AI Assistant",
                response.get("response", ""),
                used_tools,
            )

            # Save updated agent state to session (only for session-based auth)
            # if hasattr(request, "session"): session["agent_data"] = agent.to_dict()

            # Return chat data with tool usage information
            chat_data = chat.to_dict()
            chat_data["used_tools"] = response.get("used_tools", [])

            return jsonify(chat_data), 200
        else:
            return jsonify({"error": "Method not allowed"}), 405
    except Exception as e:
        logger.error(f"Error in llm_agent_endpoint: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        llm_chat_service.close()
