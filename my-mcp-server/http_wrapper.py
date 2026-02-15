"""
HTTP wrapper for MCP server
Allows calling MCP tools via HTTP instead of stdio
"""
import json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

app = FastAPI(title="MCP Server HTTP Wrapper")

# Request model
class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "MCP Server HTTP Wrapper"}

@app.post("/call_tool")
async def call_tool_http(tool_call: ToolCall):
    """
    HTTP endpoint to call MCP tools
    """
    try:
        tool_name = tool_call.name
        arguments = tool_call.arguments
        
        if tool_name == "get_user_info":
            user_id = arguments.get("user_id", "unknown")
            result = {
                "id": user_id,
                "name": f"User {user_id}",
                "email": f"user{user_id}@example.com",
                "role": "developer"
            }
            return {
                "success": True,
                "tool": tool_name,
                "result": json.dumps(result, indent=2)
            }
        
        elif tool_name == "calculate":
            operation = arguments.get("operation", "add")
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b == 0:
                    return {
                        "success": False,
                        "tool": tool_name,
                        "error": "Division by zero"
                    }
                result = a / b
            else:
                return {
                    "success": False,
                    "tool": tool_name,
                    "error": f"Unknown operation: {operation}"
                }
            
            return {
                "success": True,
                "tool": tool_name,
                "result": f"Result: {result}"
            }
        
        else:
            return {
                "success": False,
                "tool": tool_name,
                "error": f"Unknown tool: {tool_name}"
            }
    
    except Exception as e:
        return {
            "success": False,
            "tool": tool_call.name,
            "error": str(e)
        }

@app.get("/tools")
async def list_tools_http():
    """List available tools"""
    return {
        "tools": [
            {
                "name": "get_user_info",
                "description": "Get information about a user by their ID"
            },
            {
                "name": "calculate",
                "description": "Perform basic mathematical calculations"
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
