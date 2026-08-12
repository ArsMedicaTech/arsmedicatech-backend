import asyncio
import logging
from types import TracebackType
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

    @staticmethod
    def _inject_session_headers(
        config: Dict[str, Any],
        session_token: Optional[str],
        trusted_hosts: Optional[Sequence[str]],
    ) -> Dict[str, Any]:
        """
        Attach an x-session-token header (the encrypted OpenAI API key) to
        remote MCP servers so tools that need per-user credentials (e.g. `rag`)
        can read them the same way v1's `fetch_mcp_tool_defs` wrapper did.

        :param config: Base MCP configuration (mcpServers dict).
        :param session_token: Encrypted OpenAI API key to forward as a header.
        :param trusted_hosts: If provided, only servers whose host is in this
            list receive the header, to avoid leaking the token to arbitrary
            client-supplied MCP servers.
        :return: A new config dict with headers injected; the input is not mutated.
        """
        if not session_token:
            return config

        cfg = json.loads(json.dumps(config))  # deep copy; don't mutate caller's config
        for name, server in cfg.get("mcpServers", {}).items():
            url = server.get("url")
            if not url:
                continue  # stdio server, no headers to attach
            if trusted_hosts is not None:
                host = urlparse(url).hostname or ""
                if host not in trusted_hosts:
                    logger.info(
                        f"Skipping session header for untrusted MCP server: {name}"
                    )
                    continue
            server.setdefault("headers", {})["x-session-token"] = session_token
        return cfg

    async def __aenter__(self):
        """
        Connects to all configured MCP servers and builds the tool/resource lists.

        Establishes the connection, discovers all capabilities, and prepares the manager for use.
        """
        logger.info("Connecting to MCP servers and discovering capabilities...")
        await self.client.__aenter__()  # Enter the client's context

        try:
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
            # Ensure we disconnect if setup fails
            logger.error(f"Failed to connect or discover agents: {e}")
            await self.client.__aexit__(type(e), e, e.__traceback__)
            raise  # Re-raise the exception to the caller

        return self  # Return the instance for use in the 'as' clause

    async def __aexit__(
        self, exc_type: type, exc_val: Exception, exc_tb: TracebackType
    ):
        """
        Ensures the client connection is closed when exiting the context.
        """
        logger.info("Disconnecting from MCP servers.")
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

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
