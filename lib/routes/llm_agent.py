"""
LLM Agent Endpoint
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, cast

from flask import Response, jsonify, request

from lib.data_types import UserID
from lib.llm.agent import (
    DEFAULT_SYSTEM_PROMPT,
    LLMAgent,
    LLMModel,
    ToolDefinition,
    merge_mcp_configs,
)
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
    client_mcp_config: Optional[Dict[str, Any]] = None,
    **kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handles the entire async workflow for getting a response from the LLM agent.

    :param mcp_conf: Base server-side MCP configuration
    :param api_key: API key for accessing the LLM service
    :param prompt: User prompt to send to the LLM
    :param history: Conversation history
    :param response_format: Format for the LLM's response
    :param client_mcp_config: Optional client-side MCP configuration to merge with server config
    :param kwargs: Additional parameters
    :return: Dict containing the LLM's response and tool usage information
    """
    # Merge client config with server config if provided
    merged_config = merge_mcp_configs(mcp_conf, client_mcp_config)
    manager = HierarchicalAgentManager(merged_config)

    async with manager:
        system_prompt_val = kwargs.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        system_prompt: str = (
            system_prompt_val
            if isinstance(system_prompt_val, str)
            else DEFAULT_SYSTEM_PROMPT
        )

        agent = LLMAgent(
            api_key=api_key,
            model=LLMModel.GPT_5_NANO,
            system_prompt=system_prompt,
        )

        # 3) Wire the manager's discovered tools into the agent
        agent.tool_definitions = cast(List[ToolDefinition], manager.openai_defs)
        agent.tool_func_dict = manager.func_lookup

        # 4) Set the conversation history from the database
        # History is already in the correct format from get_thread_history
        # (list of dicts with 'role' and 'content' keys)
        agent.message_history = history

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
            # Support both new thread-based and legacy chat retrieval
            assistant_id = request.args.get("assistant_id")
            threads = llm_chat_service.get_threads_for_user(
                UserID(current_user_id), assistant_id
            )
            return jsonify([thread.to_dict() for thread in threads]), 200
        elif request.method == "POST":
            data: Optional[Dict[str, Any]] = request.json
            if data is None:
                return jsonify({"error": "Invalid JSON data"}), 400

            assistant_id = data.get("assistant_id", "ai-assistant")
            prompt = data.get("prompt")
            if not prompt:
                return jsonify({"error": "No prompt provided"}), 400

            # Determine thread ID: either provided directly or find/create based on context
            thread_id = data.get("thread_id")
            context = data.get(
                "context", {}
            )  # e.g., {patient_id: '...', care_plan_id: '...'}

            if not thread_id:
                if not context:
                    # For backward compatibility, allow requests without context
                    # In this case, we'll create/find a thread with no patient/care_plan context
                    logger.debug(
                        "[DEBUG] No thread_id or context provided, creating thread without context"
                    )
                thread_id = llm_chat_service.get_or_create_thread(
                    user_id=UserID(current_user_id),
                    assistant_id=assistant_id,
                    context=context,
                )
            else:
                # Validate that the thread exists and belongs to the user
                thread = llm_chat_service.get_thread(thread_id)
                if not thread:
                    return jsonify({"error": "Thread not found"}), 404
                if str(thread.user_id) != str(current_user_id):
                    return jsonify({"error": "Unauthorized access to thread"}), 403

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

            # Add user message to thread (atomic insert)
            llm_chat_service.add_message(
                thread_id=thread_id, role="user", content=prompt
            )

            response_format = data.get("response_format")  # type: ignore

            # Retrieve thread history for LLM context
            history: list[Dict[str, Any]] = llm_chat_service.get_thread_history(
                thread_id
            )
            logger.debug(f"History: {history}")

            agent_mcp_config = (
                dict(cast(Dict[str, Any], mcp_config))
                if AGENT_VERSION == "v2"
                else {"url": MCP_URL}  # Adapt based on your config structure
            )

            # Extract client-side MCP config from request if provided
            client_mcp_config = data.get("mcp_config")  # type: ignore
            if client_mcp_config and not isinstance(client_mcp_config, dict):
                return jsonify({"error": "mcp_config must be a dictionary"}), 400

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
                        client_mcp_config=client_mcp_config,
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

            # Add assistant response to thread (atomic insert)
            used_tools = response.get("used_tools", [])
            llm_chat_service.add_message(
                thread_id=thread_id,
                role="assistant",
                content=response.get("response", ""),
                used_tools=used_tools,
            )

            # Retrieve the updated thread to return to client
            thread = llm_chat_service.get_thread(thread_id)
            if not thread:
                return jsonify({"error": "Failed to retrieve thread"}), 500

            # Get all messages for the thread to return complete conversation
            messages = llm_chat_service.get_thread_history(thread_id)

            # Return thread data with messages and tool usage information
            response_data = thread.to_dict()
            response_data["messages"] = messages
            response_data["thread_id"] = thread_id
            response_data["used_tools"] = used_tools

            return jsonify(response_data), 200
        else:
            return jsonify({"error": "Method not allowed"}), 405
    except Exception as e:
        logger.error(f"Error in llm_agent_endpoint: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        llm_chat_service.close()


def link_chat_thread_route(thread_id: str) -> Tuple[Response, int]:
    """
    Route for linking a chat thread to a care plan (Adoption Pattern).
    Used when a draft thread needs to be associated with a newly created care plan.

    :param thread_id: The thread ID to link (from URL parameter).
    :return: Response object with success status or error message.
    """
    logger.debug(f"[DEBUG] /api/llm_chat/thread/{thread_id}/link called")

    # Get current user from auth decorator (either session or API key)
    current_user = get_current_user()
    if not current_user:
        logger.debug("[DEBUG] Not authenticated in link_chat_thread")
        return jsonify({"error": "Not authenticated"}), 401

    current_user_id = current_user.user_id
    logger.debug(f"[DEBUG] User authenticated: {current_user_id}")

    llm_chat_service = LLMChatService()
    llm_chat_service.connect()
    try:
        # Security: Ensure current user owns this thread
        thread = llm_chat_service.get_thread(thread_id)
        if not thread:
            return jsonify({"error": "Thread not found"}), 404

        if str(thread.user_id) != str(current_user_id):
            return jsonify({"error": "Unauthorized access to thread"}), 403

        # Get the new context from request body
        data: Optional[Dict[str, Any]] = request.json
        if data is None:
            return jsonify({"error": "Invalid JSON data"}), 400

        # Build the update context
        new_context_fields: Dict[str, Any] = {}

        # Handle care_plan_id adoption
        if "care_plan_id" in data:
            care_plan_id = data.get("care_plan_id")
            new_context_fields["care_plan_id"] = care_plan_id
            # Clear draft_session_id when adopting to a real care plan
            if care_plan_id is not None:
                new_context_fields["draft_session_id"] = None

        # Allow updating patient_id if needed
        if "patient_id" in data:
            new_context_fields["patient_id"] = data.get("patient_id")

        if not new_context_fields:
            return jsonify({"error": "No context fields provided for update"}), 400

        # Update the thread context
        updated_thread = llm_chat_service.update_thread_context(
            thread_id, new_context_fields
        )

        if not updated_thread:
            return jsonify({"error": "Failed to update thread context"}), 500

        logger.debug(
            f"Successfully linked thread {thread_id} with context: {new_context_fields}"
        )

        return jsonify({"status": "success", "thread": updated_thread.to_dict()}), 200

    except Exception as e:
        logger.error(f"Error in link_chat_thread: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        llm_chat_service.close()
