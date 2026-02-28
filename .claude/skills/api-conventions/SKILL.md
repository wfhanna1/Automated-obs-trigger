---
name: api-conventions
description: Azure Functions and Service Bus message conventions for this project. Applied automatically when working on function_app.py or Service Bus message schemas.
---

# Azure Functions & Message Conventions

## HTTP Function Conventions (LoadSchedule)

### Route Pattern
- Route: `/api/<kebab-case-name>`
- Example: `/api/load-schedule`

### HTTP Methods
- Use explicit `methods=["POST"]` on `@app.route` for mutation operations
- Trigger responses return `func.HttpResponse` with appropriate status codes

### Response Status Codes
- `200` - Success
- `207` - Partial success (some messages enqueued, some failed)
- `400` - Bad request (schedule validation error)
- `500` - Internal config error (missing env vars)
- `502` - Upstream fetch failure (GitHub or servers.yaml unavailable)

### Error Response Body
- Plain text describing the error — no JSON envelope needed for internal automation endpoints
- Include enough context to diagnose without exposing credentials

### Environment Variable Access Pattern
```python
def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value
```
Always use this pattern. Never use `os.environ[name]` directly (raises `KeyError` with less context).

## Service Bus Message Conventions (OBSControl)

### Message Schema
```json
{
  "command":   "start" | "stop",
  "server_id": "<id matching servers.yaml>",
  "action":    "recording" | "streaming"
}
```

### Message Routing
- Queue name: `obs-jobs`
- Scheduled delivery via `msg.scheduled_enqueue_time_utc` (must be naive UTC datetime — strip `tzinfo`)
- One START message and one STOP message per schedule entry

### Error Handling in Service Bus Triggers
- Malformed JSON or missing keys: log and return (no re-raise — message dead-letters after max delivery count)
- Config/infra errors (Key Vault unavailable, servers.yaml fetch failed): re-raise to trigger Azure retry
- SSH/WebSocket failures: re-raise to trigger Azure retry / dead-letter

## Key Vault Secret Naming Convention

| Secret Name | Value |
|---|---|
| `ssh-key-<server-id-with-hyphens>` | Base64-encoded PEM private key |
| `obs-ws-password-<server-id-with-hyphens>` | OBS WebSocket password |

Server IDs use underscores (e.g., `win-server-1`). Key Vault names use hyphens.
Conversion: `kv_id = server_id.replace("_", "-")`

## servers.yaml Schema

```yaml
servers:
  <server-id>:
    name: "Human-readable name"
    platform: windows | mac
    host: "<IP or hostname>"
    ssh:
      user: "<username>"
      port: 22
    obs:
      path: "<full path to OBS executable>"
      websocket_port: 4455
```

## Logging Conventions

Use module-level logger in each file:
```python
logger = logging.getLogger(__name__)
```

Log levels:
- `logger.info(...)` — normal operation events (triggered, started, stopped, enqueued)
- `logger.warning(...)` — recoverable issues (SSH retry, WebSocket retry)
- `logger.error(...)` — failures that need attention
- `logger.debug(...)` — internal state useful for development (SSH exec commands, port numbers)

Never log: SSH key PEM content, OBS passwords, or Service Bus connection strings.
