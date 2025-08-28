import asyncio
import logging
from typing import Any, Callable, Dict, List

from fastmcp import Client

# Assuming mcp_config is imported from another file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HierarchicalAgentManager:
    """
    Manages a single, persistent connection to multiple MCP servers,
    presenting a unified, hierarchical interface of their capabilities.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = Client(self.config)
        self.openai_defs: List[Dict[str, Any]] = []
        self.func_lookup: Dict[str, Callable[..., Any]] = {}
        self.resources: List[Any] = []  # You can store resource info here
        self.prompts: List[Any] = []  # You can store prompt info here

    async def connect_and_discover(self) -> None:
        """
        Connects to all configured MCP servers and builds the tool/resource lists.
        """
        logger.info("Connecting to MCP servers and discovering capabilities...")
        try:
            await self.client.__aenter__()  # Manually enter the context

            # Fetch everything from all agents in parallel
            all_tools, self.resources, self.prompts = await asyncio.gather(
                self.client.list_tools(),
                self.client.list_resources(),
                self.client.list_prompts(),
            )

            logger.info(
                f"Discovered {len(all_tools)} tools, {len(self.resources)} resources, and {len(self.prompts)} prompts."
            )

            # Process the discovered tools
            for tool in all_tools:
                # The tool.name is now automatically prefixed, e.g., "code_analyst_review_code"
                self.openai_defs.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": {
                                "type": "object",
                                "properties": tool.inputSchema.get("properties", {}),
                                "required": tool.inputSchema.get("required", []),
                            },
                        },
                    }
                )
                self.func_lookup[tool.name] = self._create_tool_caller(tool.name)

        except Exception as e:
            logger.error(f"Failed to connect or discover agents: {e}")
        # The connection will be kept open until we call disconnect

    def _create_tool_caller(self, tool_name: str) -> Callable[..., Any]:
        """Creates a wrapper to call a specific tool using the persistent client."""

        async def _call(**kwargs: Any) -> Any:
            logger.info(f"Calling hierarchical tool: {tool_name} with args: {kwargs}")
            try:
                # Use the single, persistent self.client
                result = await self.client.call_tool(tool_name, kwargs)
                # Your existing result handling logic
                if hasattr(result, "structured_content"):
                    return result.structured_content or result.content
                return result.content or result
            except Exception as e:
                logger.error(f"Error calling tool {tool_name}: {e}")
                return {"error": str(e)}

        return _call

    async def disconnect(self) -> None:
        """Closes the connection to all servers."""
        logger.info("Disconnecting from MCP servers.")
        await self.client.__aexit__(None, None, None)
