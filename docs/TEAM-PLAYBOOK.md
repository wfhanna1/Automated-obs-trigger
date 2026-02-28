# Enterprise Agent Team Playbook

## How This Team Works

This project is maintained by a coordinated Claude Code agent team. Each agent is a specialized
Claude Code instance with a defined role, file ownership boundaries, and communication protocols.

---

## Agent Team Roles

| Agent | Domain | File Ownership | Key Responsibilities |
|---|---|---|---|
| **Tech Lead** | Architecture & Coordination | `.claude/`, `docs/` | Break down work, review plans, synthesize results, enforce quality gates |
| **Backend Engineer** | Azure Functions & OBS Logic | `function_app.py`, `src/` | Function implementation, schedule parsing, SSH/WebSocket logic |
| **Platform Engineer** | Infrastructure & CI/CD | `infra/`, `.github/` | Bicep IaC, GitHub Actions, Azure resource configuration, deployment |
| **QA Engineer** | Testing & Quality | `tests/` | Write pytest suites, run tests, validate changes, report failures |
| **Security Reviewer** | Security Audit | Read-only | SSH key handling review, secrets audit, OWASP Top 10 check |
| **Code Reviewer** | Code Quality | Read-only | Clean code review, SOLID compliance, architecture consistency |

---

## 1. Intent-Based Leadership ("Turn the Ship Around")

Agents communicate **intent**, not requests:
- "I intend to add retry logic to the WebSocket connection, using exponential backoff" — not "Can I change the retry logic?"
- Tech Lead can redirect or approve, but agents act on their own initiative within their domain

---

## 2. The Five Dysfunctions Framework

**Trust**: Agents share findings openly. No information hoarding.
**Healthy Conflict**: Code Reviewer and Security Reviewer are expected to challenge approaches.
**Commitment**: Once the Tech Lead approves a plan, all agents align.
**Accountability**: QA Engineer validates independently. Agents mark tasks complete only when quality gates pass.
**Results**: Shared task list tracks outcomes (working code), not activity (files touched).

---

## 3. Communication Protocols

### Task Flow
```
User → Tech Lead → Creates tasks → Agents claim + work → Report back → Tech Lead synthesizes
```

### Key Inter-Agent Contracts
- **Backend → Platform**: "I need a new env var `FOO` — please add it to Bicep and document it in the README"
- **Backend → Security**: "I changed SSH key handling in `remote_controller.py` — please review"
- **QA → Backend**: "Test `test_load_schedule_invalid_timezone` fails — here's the reproduction"
- **Security → Tech Lead**: "[HIGH] SSH private key is logged in `launch_obs` at line X"

---

## 4. Quality Gates (Automated)

Every task must pass before completion (enforced by `scripts/task-completed-gate.sh`):

- `python -m ruff check .` passes
- `python -m mypy src function_app.py --ignore-missing-imports` passes
- `python -m pytest tests/unit tests/integration -q` passes (E2E excluded from gate)

---

## 5. Weekly Workflow

1. Fill in `schedules/current_week.csv` with the new week's sessions
2. Commit and push to `main`
3. GitHub Actions calls `LoadSchedule` automatically
4. Jobs are enqueued in Azure Service Bus with exact UTC delivery times
5. At each scheduled time, `OBSControl` fires and starts/stops OBS on the correct machine
6. Monitor via Azure Portal → Function App → Monitor, or Application Insights

---

## 6. Deployment Process

### Infrastructure (one-time or on changes)
```bash
# Via GitHub Actions (recommended)
git push  # deploy-infra.yml triggers on infra/ changes

# Or manually
az deployment group create \
  -g obs-scheduler-rg \
  -f infra/main.bicep \
  -p functionAppName=obs-scheduler serviceBusNamespace=obs-scheduler-sb keyVaultName=obs-scheduler-kv
```

### Function App Code
```bash
func azure functionapp publish obs-scheduler
```
Or via GitHub Actions (add a deploy-functions workflow).

### Required GitHub Actions Secrets
| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | Service principal JSON |
| `AZURE_FUNCTION_BASE_URL` | `https://obs-scheduler.azurewebsites.net` |
| `AZURE_FUNCTION_KEY` | Function-level API key |
