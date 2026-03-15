import os
from agents.mcp import MCPServerStreamableHttp
from utils import get_access_token


async def get_aws_mcp_server() -> MCPServerStreamableHttp:
    token = get_access_token()
    return MCPServerStreamableHttp(
        name="Streamable HTTP Python Server",
        params={
            "url": os.getenv("MCP_URL"),
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": 10,
        },
        cache_tools_list=True,
        max_retry_attempts=3,
    )
