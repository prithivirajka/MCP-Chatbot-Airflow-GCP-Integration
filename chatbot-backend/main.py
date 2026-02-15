from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging
import ollama
import json
import re
import httpx

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatbot API with Ollama and MCP")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class ChatResponse(BaseModel):
    response: str
    tool_uses: Optional[List[dict]] = None

@app.get("/")
async def root():
    return {
        "message": "Chatbot API with Ollama is running",
        "model": "llama3.2",
        "endpoints": {
            "health": "/health",
            "chat": "/chat (POST)",
            "models": "/models",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Check if API and Ollama are running"""
    try:
        # Test if Ollama is accessible
        models = ollama.list()
        model_names = []
        if hasattr(models, 'models'):
            model_names = [model.model for model in models.models]
        elif isinstance(models, dict) and 'models' in models:
            model_names = [model['name'] for model in models['models']]
        
        return {
            "status": "healthy",
            "ollama_running": True,
            "available_models": model_names
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "ollama_running": False,
            "error": str(e)
        }

@app.get("/models")
async def list_models():
    """List available Ollama models"""
    try:
        models = ollama.list()
        model_names = []
        if hasattr(models, 'models'):
            model_names = [model.model for model in models.models]
        elif isinstance(models, dict) and 'models' in models:
            model_names = [model['name'] for model in models['models']]
        
        return {
            "models": model_names
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Handle chat requests with MCP tool integration using Ollama
    """
    try:
        logger.info(f"Received chat request with {len(request.messages)} messages")
        
        # Convert messages to Ollama format
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        # Add system message with tool instructions
        system_message = {
            "role": "system",
            "content": """You are a helpful assistant with access to tools. 
            
Available tools:
1. get_user_info - Get information about a user by their ID
   Usage: [TOOL:get_user_info:user_id=123]

2. calculate - Perform calculations (add, subtract, multiply, divide)
   Usage: [TOOL:calculate:operation=add,a=10,b=5]

When you need to use a tool, include the tool call in your response using the format above.
After using a tool, explain the result to the user naturally."""
        }
        
        messages.insert(0, system_message)
        
        # Call Ollama
        response = ollama.chat(
            model='llama3.2',
            messages=messages
        )
        
        response_text = response['message']['content']
        logger.info(f"Ollama response: {response_text[:100]}...")
        
        # Check if response contains tool calls
        tool_uses = []
        
        # Simple tool detection pattern: [TOOL:tool_name:param=value,param=value]
        tool_pattern = r'\[TOOL:(\w+):([^\]]+)\]'
        tool_matches = re.finditer(tool_pattern, response_text)
        
        for match in tool_matches:
            tool_name = match.group(1)
            params_str = match.group(2)
            
            # Parse parameters
            params = {}
            for param in params_str.split(','):
                if '=' in param:
                    key, value = param.split('=', 1)
                    # Try to convert to number if possible
                    try:
                        value = float(value)
                        if value.is_integer():
                            value = int(value)
                    except ValueError:
                        pass  # Keep as string
                    params[key.strip()] = value
            
            logger.info(f"Tool detected: {tool_name} with params: {params}")
            
            # Execute tool
            tool_result = execute_mcp_tool(tool_name, params)
            
            tool_uses.append({
                "name": tool_name,
                "input": params,
                "result": tool_result
            })
            
            # Replace tool call with result in response
            response_text = response_text.replace(
                match.group(0),
                f"\n[Tool Result: {tool_result}]\n"
            )
        
        # If tools were used, get a follow-up response
        if tool_uses:
            messages.append({
                "role": "assistant",
                "content": response['message']['content']
            })
            messages.append({
                "role": "user",
                "content": f"Tool results: {json.dumps([t['result'] for t in tool_uses])}. Please explain these results naturally to the user."
            })
            
            follow_up = ollama.chat(
                model='llama3.2',
                messages=messages
            )
            
            response_text = follow_up['message']['content']
        
        return ChatResponse(
            response=response_text,
            tool_uses=tool_uses if tool_uses else None
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def execute_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Execute MCP tool by calling the HTTP wrapper server at localhost:8001
    """
    try:
        # MCP HTTP wrapper endpoint
        mcp_server_url = "http://localhost:8001/call_tool"
        
        # Prepare the request payload
        payload = {
            "name": tool_name,
            "arguments": arguments
        }
        
        logger.info(f"Calling MCP HTTP wrapper at {mcp_server_url} with tool: {tool_name}")
        
        # Make HTTP request to MCP server
        with httpx.Client(timeout=30) as client:
            response = client.post(mcp_server_url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"MCP server returned: {result}")
                
                # Extract the result from the response
                if isinstance(result, dict):
                    if result.get('success'):
                        return result.get('result', 'Tool executed')
                    else:
                        error_msg = f"Tool error: {result.get('error', 'Unknown error')}"
                        logger.error(error_msg)
                        return error_msg
                
                return json.dumps(result, indent=2)
            else:
                error_msg = f"MCP server error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return error_msg
                
    except Exception as e:
        error_msg = f"Error calling MCP server: {str(e)}"
        logger.error(error_msg)
        # Fallback to simulated response if MCP server is not available
        logger.warning(f"Falling back to simulated tool response for {tool_name}")
        return fallback_execute_tool(tool_name, arguments)

def fallback_execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Fallback simulated tool execution if MCP server is unavailable
    """
    try:
        if tool_name == "get_user_info":
            user_id = arguments.get("user_id", "unknown")
            result = {
                "id": user_id,
                "name": f"User {user_id}",
                "email": f"user{user_id}@example.com",
                "role": "developer"
            }
            return json.dumps(result, indent=2)
        
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
                    return "Error: Division by zero"
                result = a / b
            else:
                return f"Unknown operation: {operation}"
            
            return f"Result: {result}"
        
        return "Tool executed successfully"
        
    except Exception as e:
        logger.error(f"Error in fallback tool execution {tool_name}: {str(e)}")
        return f"Error: {str(e)}"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
