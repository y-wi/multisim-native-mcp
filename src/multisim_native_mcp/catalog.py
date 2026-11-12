"""A preferred tool catalog with callable compatibility aliases."""
from mcp.server.mcpserver import MCPServer

COMPATIBILITY_TOOLS={
    'native_connect_pins':'native_connect_endpoints',
    'native_delete_text':'native_delete_object',
}


class NativeMCPServer(MCPServer):
    async def list_tools(self):
        return [tool for tool in await super().list_tools() if tool.name not in COMPATIBILITY_TOOLS]
