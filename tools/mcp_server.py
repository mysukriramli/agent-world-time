#!/usr/bin/env python3
"""
tools/mcp_server.py - Zero-dependency stdio MCP server for agent clients.
"""
import sys, json
from time_tool import convert_time, calculate_offset, calculate_business_days

def handle_rpc(request):
    method = request.get("method")
    req_id = request.get("id")

    if method == "tools/list":
        with open("tools/function_schemas.json") as f:
            schemas = json.load(f)
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": schemas["tools"]}}

    elif method == "tools/call":
        params = request["params"]
        name = params["name"]
        args = params["arguments"]
        
        if name == "world_time_convert":
            res = convert_time(args["iso_timestamp"], args["from_timezone"], args["to_timezone"])
        elif name == "world_time_math":
            res = calculate_offset(args["iso_timestamp"], args.get("timezone", "UTC"), 
                                   args.get("days", 0), args.get("hours", 0))
        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

if __name__ == "__main__":
    for line in sys.stdin:
        if line.strip():
            req = json.loads(line)
            sys.stdout.write(json.dumps(handle_rpc(req)) + "\n")
            sys.stdout.flush()
