"""ElevenLabs webhook tools, generated from the backend's own FastAPI definitions.

Every POST /tools/* route becomes one tool: same name, same description, same parameters. Change a
tool in the backend and the next deploy updates the agent, so the two can never drift apart."""

from fastapi import FastAPI

PUBLIC_URL_PLACEHOLDER = "{{PUBLIC_URL}}"
SECRET_PLACEHOLDER = "{{STORMDESK_TOOL_SECRET}}"

# The conversation id is filled in by ElevenLabs itself, never by the AI, so it can't be faked.
CONVERSATION_ID_VARIABLE = "system__conversation_id"

# Most tools answer in well under a second; live status checks can take a few seconds when a status
# page is slow; check_approval_status deliberately waits up to 12 s for the technician.
TIMEOUTS = {"check_approval_status": 25}
DEFAULT_TIMEOUT = 15
SLOW_TOOLS = {"check_approval_status", "check_service_status", "check_security_advisories", "check_device_health"}


def _resolve(spec: dict, schema: dict) -> dict:
    if "$ref" in schema:
        return spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _property(name: str, schema: dict) -> dict:
    if name == "conversation_id":
        return {"type": "string", "dynamic_variable": CONVERSATION_ID_VARIABLE}
    value = schema
    if "anyOf" in schema:  # Optional[X] in pydantic is anyOf [X, null]
        value = next(option for option in schema["anyOf"] if option.get("type") != "null")
    prop = {"type": value["type"], "description": schema.get("description") or value.get("description", "")}
    if "enum" in value:
        prop["enum"] = value["enum"]
    return prop


def body_schema(spec: dict, route: dict, tool_name: str) -> dict:
    schema = _resolve(spec, route["requestBody"]["content"]["application/json"]["schema"])
    properties = {name: _property(name, prop) for name, prop in schema.get("properties", {}).items()}
    required = [name for name in schema.get("required", []) if name in properties]
    if "conversation_id" in properties and "conversation_id" not in required:
        required.insert(0, "conversation_id")  # always sent, so every call lands in the audit trail
    return {
        "type": "object",
        "description": f"Arguments for {tool_name}",
        "properties": properties,
        "required": required,
    }


def build_tools(app: FastAPI, public_url: str = PUBLIC_URL_PLACEHOLDER,
                secret: dict | str = SECRET_PLACEHOLDER) -> list[dict]:
    """One ElevenLabs tool_config per backend tool. `secret` is {"secret_id": ...} once stored in ElevenLabs."""
    spec = app.openapi()
    tools = []
    for path, methods in spec["paths"].items():
        if not path.startswith("/tools/") or "post" not in methods:
            continue
        route = methods["post"]
        name = path.removeprefix("/tools/")
        tools.append({
            "type": "webhook",
            "name": name,
            "description": route.get("description") or route.get("summary", name),
            "response_timeout_secs": TIMEOUTS.get(name, DEFAULT_TIMEOUT),
            "tool_call_sound": "typing" if name in SLOW_TOOLS else None,
            "api_schema": {
                "url": f"{public_url.rstrip('/')}/tools/{name}",
                "method": "POST",
                "request_headers": {"X-StormDesk-Key": secret, "ngrok-skip-browser-warning": "1"},
                "request_body_schema": body_schema(spec, route, name),
            },
        })
    return sorted(tools, key=lambda t: t["name"])
