# Automated OBS Trigger - Project Guide

## Project Overview

Serverless automation that starts and stops OBS Studio on remote Windows and Mac machines
according to a variable weekly schedule. Built on Azure Functions (Python 3.11) + Azure
Service Bus + Azure Key Vault. Two Azure Functions: `LoadSchedule` (HTTP trigger, reads
CSV from GitHub and enqueues timed Service Bus messages) and `OBSControl` (Service Bus
trigger, SSHes into the remote machine and controls OBS via WebSocket).

## Team Operating Principles

### Leadership Model: Intent-Based Leadership ("Turn the Ship Around")

- Agents communicate **intent**, not requests: "I intend to refactor the schedule loader" not "Can I refactor?"
- Push decision-making authority to the agent closest to the information
- Leader-leader model: every agent owns their domain and makes decisions within it
- The Tech Lead agent coordinates, but does NOT micromanage. Agents are empowered.

### Team Health: The Five Dysfunctions of a Team (Lencioni)

1. **Trust** - Agents share findings openly via messaging; no information hoarding
2. **Healthy Conflict** - Competing hypotheses are encouraged (e.g., parallel debugging)
3. **Commitment** - Once a plan is approved, all agents align and execute
4. **Accountability** - Each agent owns their deliverables and marks tasks complete honestly
5. **Results** - The shared task list tracks outcomes, not activity

### Product Mindset

- Every change must tie to a user outcome, not just a technical improvement
- Prefer small, shippable increments over large batches
- Validate assumptions before building. Ask "who benefits and how?"
- Measure success by impact delivered, not code volume

## Architecture: 12-Factor App Principles

1. **Codebase** - One repo, tracked in git, many deploys
2. **Dependencies** - Explicitly declared in `requirements.txt`; never rely on system packages
3. **Config** - Stored in Azure Function App settings (environment variables), never in code
4. **Backing Services** - Azure Service Bus and Key Vault are attached resources via connection strings/URIs from env vars
5. **Build/Release/Run** - CI builds; `func azure functionapp publish` releases; Azure runs
6. **Processes** - Stateless Azure Functions; no in-process state between invocations
7. **Port Binding** - Azure Functions handle port binding; OBS WebSocket tunnel is ephemeral
8. **Concurrency** - Azure Functions scale out via the process model
9. **Disposability** - Functions are ephemeral by nature; SSH tunnels cleaned up in context managers
10. **Dev/Prod Parity** - Same backing services locally (local.settings.json) and in prod
11. **Logs** - All logs via `logging` to stdout/stderr; captured by Azure Application Insights
12. **Admin Processes** - One-off tasks run via `func start` or direct Python invocation

## Clean Code Standards

- **SOLID Principles**: Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- **Meaningful Names**: Variables, functions, classes must reveal intent
- **Small Functions**: Each function does one thing; max ~20 lines preferred
- **DRY**: Don't Repeat Yourself. Extract shared logic, but avoid premature abstraction
- **No Magic Numbers/Strings**: Use named constants (see `WS_RETRY_INTERVAL`, `SSH_MAX_RETRIES`, etc.)
- **Error Handling**: Fail fast, use typed errors, never swallow exceptions silently
- **Testing**: Every public function must have tests; prefer unit tests, supplement with integration

## Project Structure

```
Automated-obs-trigger/
├── function_app.py              # Azure Functions entry point (LoadSchedule + OBSControl)
├── host.json                    # Functions host config (timeout, extensions)
├── requirements.txt             # Python dependencies
├── .github/
│   └── workflows/
│       ├── deploy-infra.yml     # Azure infra deployment workflow
│       └── load-schedule.yml    # Auto-trigger LoadSchedule on CSV push
├── config/
│   ├── servers.yaml             # Server configs (gitignored — no secrets)
│   └── servers.example.yaml    # Documented example for new contributors
├── schedules/
│   ├── schedule_template.csv   # Blank template for weekly schedules
│   └── current_week.csv        # Active schedule (replace each week)
├── src/
│   ├── __init__.py
│   ├── schedule_loader.py       # CSV parser + validator
│   ├── remote_controller.py     # SSH OBS launch/kill + tunnel context manager
│   └── obs_websocket.py         # OBS WebSocket v5 start/stop
├── infra/
│   └── main.bicep               # Azure Bicep IaC (Functions, Service Bus, Key Vault, Storage)
├── tests/                       # All tests (owned by QA Engineer)
├── .claude/                     # Agent team configuration
├── scripts/                     # Quality enforcement hook scripts
└── docs/                        # Architecture decisions + team playbook
```

## File Ownership Rules (Conflict Prevention)

IMPORTANT: To avoid agent file conflicts, respect these ownership boundaries:

| Agent | Owns | Cannot Modify |
|---|---|---|
| **Backend Engineer** | `function_app.py`, `src/` | `infra/`, `.github/` |
| **Platform Engineer** | `infra/`, `.github/`, `host.json`, `requirements.txt` | `function_app.py`, `src/` |
| **QA Engineer** | `tests/` | All source files |
| **Security Reviewer** | Read-only | Everything |
| **Code Reviewer** | Read-only | Everything |
| **Tech Lead** | `.claude/`, `docs/` | Implementation files |

Shared config files (`config/servers.example.yaml`, `schedules/`) may be edited by either
Backend or Platform Engineer — coordinate via the Tech Lead when both need changes.

## Workflow Commands

- **Install**: `pip install -r requirements.txt`
- **Test**: `python -m pytest`
- **Single Test**: `python -m pytest -k "test_name"`
- **Lint**: `python -m ruff check .`
- **Type Check**: `python -m mypy .`
- **Run locally**: `func start`
- **Deploy Functions**: `func azure functionapp publish obs-scheduler`
- **Deploy Infra**: See `.github/workflows/deploy-infra.yml`

## Code Style

- Python 3.11+. Use modern type hints (`str | None`, `list[str]`, etc.)
- Use `@dataclass` for value types (see `ScheduleEntry`)
- Prefer `contextmanager` for resource management (see `obs_tunnel`)
- All configuration from environment variables via `os.environ.get()` — never hardcode
- Structured logging via the `logging` module. Log to stdout. No file handlers.
- Type annotate all public function signatures
- Constants in UPPER_CASE at module level (e.g., `WS_RETRY_INTERVAL`, `SSH_MAX_RETRIES`)
- Error types: raise built-ins (`RuntimeError`, `ValueError`) with clear messages;
  re-raise from Azure Functions to trigger Service Bus retry/dead-letter

## Git Conventions

- Branch naming: `feature/<description>`, `fix/<description>`, `chore/<description>`
- Commit messages: imperative mood, max 72 chars first line, body explains "why"
- Always run lint + type check before committing
- PRs require at least one review pass (use code-reviewer agent)

## Agent Team Configuration

When starting an agent team for this project, use these role assignments:

```
Create an agent team with the following structure:
- Tech Lead: coordinates work, reviews plans, synthesizes results (delegate mode)
- Backend Engineer: owns function_app.py and src/, Azure Functions logic, OBS control
- Platform Engineer: owns infra/ and .github/, Bicep IaC and GitHub Actions workflows
- QA Engineer: owns tests/, writes and runs pytest suites, validates changes
- Security Reviewer: audits for OWASP Top 10, SSH key handling, secrets exposure
- Code Reviewer: reviews clean code compliance, SOLID principles, architecture consistency
```

Each agent reads this CLAUDE.md.
Agents communicate via the shared task list and direct messaging.
The Tech Lead should use **delegate mode** (Shift+Tab) to focus on coordination.

## Quality Gates

- All code changes MUST pass `ruff check .` before commit
- All code changes MUST pass `mypy .` before commit
- All PRs MUST include tests in `tests/`
- Security-sensitive changes (SSH key handling, Key Vault access, env var usage) MUST be reviewed by security-reviewer agent
- Shared module changes (`src/`) MUST be reviewed by code-reviewer agent
