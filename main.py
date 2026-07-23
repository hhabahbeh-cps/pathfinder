import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="CPS Data MCP Server")

# Load your Swagger / API data or school metrics here
def load_cps_data(query: str):
    # This searches your CPS data for matching records
    return f"CPS Data results for '{query}': High School Graduation Rate dataset matched."


@app.get("/")
@app.get("/mcp")
@app.post("/mcp")
async def handle_mcp(request: Request):
    if request.method == "GET":
        return {"status": "active", "server": "CPS Data MCP Server"}
    
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    # 1. MCP Protocol Handshake
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "CPS-Data-Server", "version": "1.0"}
            }
        })
    
    # 2. List available tools to the AI Agent
    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "search_cps_schools",
                        "description": "Searches official Chicago Public Schools dataset and school metrics.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string", 
                                    "description": "School name, neighborhood, or metric to search"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ]
            }
        })

    # 3. Handle tool calls from the AI Agent
    elif method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})
        query = args.get("query", "")
        
        data_result = load_cps_data(query)
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": data_result
                    }
                ]
            }
        })

    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)