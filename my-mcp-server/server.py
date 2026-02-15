import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create server instance
server = Server("my-first-mcp-server")

# Define your tools
@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_user_info",
            description="Get information about a user by their ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user"
                    }
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="calculate",
            description="Perform basic mathematical calculations",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "The operation to perform"
                    },
                    "a": {
                        "type": "number",
                        "description": "First number"
                    },
                    "b": {
                        "type": "number",
                        "description": "Second number"
                    }
                },
                "required": ["operation", "a", "b"]
            }
        )
    ]

# Implement tool call handlers
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    
    if name == "get_user_info":
        user_id = arguments["user_id"]
        # Simulate fetching user data
        user_data = {
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
            "role": "developer"
        }
        return [TextContent(
            type="text",
            text=json.dumps(user_data, indent=2)
        )]
    
    elif name == "calculate":
        operation = arguments["operation"]
        a = arguments["a"]
        b = arguments["b"]
        
        result = None
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                return [TextContent(
                    type="text",
                    text="Error: Division by zero"
                )]
            result = a / b
        
        return [TextContent(
            type="text",
            text=f"Result: {result}"
        )]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# Main entry point
async def main():
    """Run the server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())