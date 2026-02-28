# Architecture Decision Records (ADRs)

Each decision follows the format:
- **Status**: Proposed | Accepted | Deprecated | Superseded
- **Context**: What situation prompted this decision?
- **Decision**: What was decided?
- **Consequences**: What trade-offs does this create?

---

## ADR-001: Azure Functions + Service Bus for Serverless Scheduling

**Status**: Accepted

**Context**: OBS needs to start and stop on remote machines at exact times without a server running continuously. A traditional cron server would require always-on infrastructure and manual maintenance.

**Decision**: Use Azure Functions (event-driven, serverless) triggered by Azure Service Bus messages with `scheduled_enqueue_time_utc` to deliver jobs at exact UTC times. LoadSchedule enqueues; OBSControl consumes.

**Consequences**:
- No always-on infrastructure (cost efficient)
- Azure Service Bus provides durable, retryable delivery with dead-lettering
- Premium EP1 is required for static outbound IPs (SSH firewall allowlisting) — adds ~$170/month base cost
- Function App must be Python 3.11+ on Linux

---

## ADR-002: SSH Tunnel for OBS WebSocket Access

**Status**: Accepted

**Context**: OBS WebSocket (port 4455) must not be exposed to the internet. The Function App needs to control OBS remotely.

**Decision**: Open an SSH tunnel from the Function App to the remote machine's OBS WebSocket port. The `obs_tunnel()` context manager encapsulates the tunnel lifecycle. WebSocket connections are made to `localhost:<tunnelled-port>`.

**Consequences**:
- OBS WebSocket is never exposed publicly (security win)
- SSH must be open on each remote machine (port 22, restricted to Function App outbound IPs)
- `sshtunnel` library writes SSH key to a tempfile — tempfile is always deleted in the `finally` block
- `AutoAddPolicy()` skips host key verification — acceptable for this use case but documented as a known trade-off

---

## ADR-003: Azure Key Vault for Secrets via Managed Identity

**Status**: Accepted

**Context**: SSH private keys and OBS WebSocket passwords must be stored securely and fetched at runtime. Storing in environment variables or GitHub Secrets would be lower security.

**Decision**: All per-server secrets stored in Azure Key Vault. Function App uses system-assigned Managed Identity with `DefaultAzureCredential` to fetch secrets at invocation time. No credentials stored in Function App settings or code.

**Consequences**:
- Secrets are never in environment variables or source control
- Key Vault access requires the Function App Managed Identity to have `get` policy
- Slight latency added per invocation for Key Vault fetch (~100ms)
- Secret naming convention: `ssh-key-<server-id>`, `obs-ws-password-<server-id>` (hyphens only)

---

## ADR-004: GitHub-Hosted CSV as Schedule Source

**Status**: Accepted

**Context**: The schedule changes weekly. It needs to be easy to update (non-technical users) and trigger automation on push.

**Decision**: Weekly schedule stored as `schedules/current_week.csv` in the GitHub repo. GitHub Actions workflow triggers `LoadSchedule` on push. LoadSchedule fetches the CSV from a GitHub raw URL at invocation time.

**Consequences**:
- Schedule updates are git-tracked (audit trail, rollback)
- Push to main = automatic scheduling (no manual trigger required)
- `GITHUB_RAW_CSV_URL` must be an env var — not user-controlled input (SSRF prevention)
- `servers.yaml` is also fetched from GitHub raw at runtime for server config

---

## ADR-005: Agent Team with File Ownership Boundaries

**Status**: Accepted

**Context**: Multiple agents editing the same files causes conflicts and overwrites. This project has distinct concerns: Azure Functions logic vs. infrastructure vs. tests.

**Decision**: Assign file ownership per agent role (see CLAUDE.md). Backend Engineer owns `function_app.py` and `src/`. Platform Engineer owns `infra/` and `.github/`. QA Engineer owns `tests/`. Reviewers are read-only.

**Consequences**:
- Prevents file conflicts between agents
- Cross-cutting changes (e.g., new env var added to both code and Bicep) require coordination via the Tech Lead
- Hook scripts enforce boundaries automatically

---

## ADR-006: 12-Factor App Architecture

**Status**: Accepted

**Context**: Azure Functions must be portable, configurable, and maintainable across environments (local dev, staging, production).

**Decision**: Follow the 12-Factor App methodology. All config via environment variables. No in-process state. Logs to stdout. Stateless invocations.

**Consequences**:
- `local.settings.json` mirrors Azure Function App settings for dev/prod parity
- Slightly more setup for new contributors (must configure all env vars)
- Enables horizontal scaling (multiple Function App instances) without code changes
