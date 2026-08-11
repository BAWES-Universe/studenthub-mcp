"""Probe StudentHub MCP locally: initialize -> tools/list -> call a few tools."""
import json
import urllib.request

URL = "http://127.0.0.1:8000/mcp"


def call(method, params=None, sid=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("User-Agent", "python-requests/2.31.0")
    if sid:
        req.add_header("Mcp-Session-Id", sid)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        # SSE responses come as "event: message\ndata: {...}" — extract the data payload
        payload = raw
        if raw.lstrip().startswith("event:") or "data: {" in raw:
            data_lines = [l[6:].strip() for l in raw.splitlines() if l.startswith("data:")]
            payload = data_lines[-1] if data_lines else raw
        return json.loads(payload), dict(resp.headers)


# 1. initialize
res, hdrs = call("initialize", {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "probe", "version": "1.0"},
})
# Session ID header is lowercase in some SDK versions — match case-insensitively
sid = next((v for k, v in hdrs.items() if k.lower() == "mcp-session-id"), "")
print("initialize:", res.get("result", {}).get("serverInfo", res))

# 2. tools/list
res, _ = call("tools/list", {}, sid)
tools = res.get("result", {}).get("tools", [])
print(f"\ntools/list: {len(tools)} tools")
for t in tools:
    print("  -", t["name"])

# 3. call a few tools
def tool_call(name, args):
    res, _ = call("tools/call", {"name": name, "arguments": args}, sid)
    return res

print("\n--- search_candidates (country=Egypt, limit 3) ---")
r = tool_call("search_candidates", {"country": "Egypt", "limit": 3})
for item in r.get("result", {}).get("content", []):
    print(item.get("text", "")[:800])

print("\n--- get_countries (limit 5) ---")
r = tool_call("get_countries", {"limit": 5})
for item in r.get("result", {}).get("content", []):
    print(item.get("text", "")[:600])

print("\n--- search_requests (status=cancelled, limit 3) ---")
r = tool_call("search_requests", {"status": "cancelled", "limit": 3})
for item in r.get("result", {}).get("content", []):
    print(item.get("text", "")[:800])

print("\n--- search_fulltimers (country=Egypt, limit 3) ---")
r = tool_call("search_fulltimers", {"country": "Egypt", "limit": 3})
for item in r.get("result", {}).get("content", []):
    print(item.get("text", "")[:800])

print("\n--- get_company_tree (company_id=1) ---")
r = tool_call("get_company_tree", {"company_id": 1})
for item in r.get("result", {}).get("content", []):
    print(item.get("text", "")[:800])

print("\n--- get_candidate_profile (id=1) ---")
r = tool_call("get_candidate_profile", {"candidate_id": 1})
for item in r.get("result", {}).get("content", []):
    txt = item.get("text", "")
    print(txt[:500])
    print("... profile sections:", [k for k in json.loads(txt).get("data", {}).keys()] if txt.startswith("{") else "?")

print("\nPROBE DONE")
