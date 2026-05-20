# Schedule Parser Automation Design

**Date:** 2026-05-19
**Status:** Approved for implementation

## Problem

The weekly streaming schedule update requires manual execution every Sunday:
fetch the church calendar, classify events, generate the CSV, create a branch,
push, open a PR, and merge. This takes 10-20 minutes of interactive work. It
should run autonomously every Sunday night without human involvement.

## Goal

Extend the existing `schedule-parser` skill to run fully automated on a cloud
schedule every Sunday night. It fetches the calendar, classifies events using
fixed rules, writes `schedules/current_week.csv`, creates a branch, pushes,
opens a PR, merges it, and emails a summary. A dry-run mode supports end-to-end
testing before the live schedule is activated.

## Out of scope

- Modifying the interactive mode of the schedule-parser (it remains unchanged)
- Any changes to the Azure Functions, Service Bus, or OBSControl logic
- A reply-based correction loop (potential future enhancement)

---

## Architecture

### Runtime

The skill runs as a **cloud-scheduled agent** via CronCreate (registered once
via the `/schedule` skill). It runs on Anthropic's infrastructure -- no local
machine needs to be on. The agent has browser access for calendar fetching and
Gmail MCP access for email.

```
CronCreate (Sunday 22:00 ET)
  → schedule-parser skill (automated mode)
      → browser: fetch Google Calendar
      → classify events using rules
      → write current_week.csv
      → git: branch, commit, push (via GITHUB_PAT)
      → gh: pr create, pr merge
      → Gmail MCP: send summary email
```

### Modes

The skill gains a `mode` parameter:

| Mode | Behavior |
|---|---|
| `interactive` | Existing behavior. Unchanged. |
| `automated` | No user Q&A. Classifies silently. Runs git/PR/email steps. |
| `automated --dry-run` | Full logic, no push/PR/merge. Sends `[DRY RUN]` email. |

---

## Event Classification Rules

Applied in automated mode. The existing schedule-parser location-to-server
logic is reused. These rules extend it with skip and fallback behavior.

| Condition | Decision |
|---|---|
| Location = St. Anthony Chapel | `mac-server-1` |
| Location = St. Mary & St. Joseph | `win-server-1` |
| Title contains: Choir, Confession, Sunday School, Servants Meeting, Youth | Skip |
| Unknown location, Sunday liturgy | `win-server-1` + flag in email |
| Unknown location, any other event | Exclude + flag in email |
| Start time | 5 min before service start |
| End time | Service end + 15 min buffer |

Every classification decision (including skips and fallbacks) is logged and
included in the email summary under "Decisions I made."

---

## Git and GitHub Operations

Executed after the CSV is written, in this order:

1. Check for stale `.git/index.lock` -- delete it if present
2. `git checkout main && git pull origin main`
3. Rename `schedules/current_week.csv` → `schedules/current_week_YYYY-MM-DD.csv`
4. `git checkout -b chore/schedule-YYYY-MM-DD`
5. `git add schedules/`
6. `git commit -m "Schedule update: week of YYYY-MM-DD"`
7. Set remote URL to `https://$GITHUB_PAT@github.com/wfhanna1/Automated-obs-trigger.git`
8. `git push origin chore/schedule-YYYY-MM-DD`
9. `gh auth login --with-token <<< $GITHUB_PAT`
10. `gh pr create --title "Schedule update: week of YYYY-MM-DD" --body "..."`
11. `gh pr merge --merge --delete-branch`

`GITHUB_PAT` is injected as an env var by CronCreate at schedule registration
time. It never appears in the repo.

In dry-run mode, steps 7-11 are skipped. The commands are printed to output
instead.

---

## Email Summary

Sent via Gmail MCP after successful merge (or in dry-run mode with
`[DRY RUN]` in the subject).

**Subject:** `Schedule loaded: week of YYYY-MM-DD` (or `[DRY RUN] Schedule loaded: week of YYYY-MM-DD`)

**Body:**

```
Week of Mon DD - Sun DD, YYYY

SCHEDULED EVENTS
Server        Date       Start   Stop    Title
mac-server-1  Wed May 20 05:25   07:45   Divine Liturgy
win-server-1  ...

DECISIONS I MADE
- Thu May 21: location unknown, defaulted to win-server-1
- Sat May 23: Choir Service skipped (rule: always skip)

PR: https://github.com/wfhanna1/Automated-obs-trigger/pull/<number>
```

On failure, a failure email is sent instead:

**Subject:** `[FAILED] Schedule automation: week of YYYY-MM-DD`

**Body:** The step that failed, the error message, and what state was left
behind (e.g., "branch was pushed but PR was not created").

---

## Cloud Schedule Configuration

Registered once via `/schedule` skill (CronCreate). Settings:

| Field | Value |
|---|---|
| Cron | `0 22 * * 0` (Sunday 10 PM ET) |
| Skill | `schedule-parser` (automated mode) |
| `GITHUB_PAT` | GitHub PAT with `repo` scope |
| `REPO_PATH` | Path or URL to this repository |

This is a one-time setup. The schedule runs indefinitely until explicitly
deleted or paused. PAT rotation is the only recurring maintenance step.

---

## Testing Plan

Three phases before the live Sunday schedule activates.

### Phase 1: Local dry run

Run the skill on this machine in `automated --dry-run` mode. Validates:
- Calendar fetch and event parsing
- Classification rules applied correctly
- CSV contents match expected output
- Git commands printed correctly (not executed)
- `[DRY RUN]` email received with correct schedule table and decisions log

Pass criteria: email received, CSV is correct, no errors.

### Phase 2: Cloud dry run

Register the schedule on the target server in `automated --dry-run` mode.
Trigger it manually. Validates:
- Browser access works from cloud agent
- Gmail MCP accessible from cloud agent
- `GITHUB_PAT` env var is accessible
- `gh` CLI available and authenticates with PAT
- `[DRY RUN]` email received

Pass criteria: email received, no auth errors, no tool access errors.

### Phase 3: Cloud live run (one-shot)

Manually trigger the full live run once from the cloud schedule. Validates:
- CSV pushed to GitHub
- PR created and merged successfully
- GitHub Action fires on merge (LoadSchedule triggered)
- Summary email received with PR link

Pass criteria: PR merged, GitHub Action green, summary email received.

Only after Phase 3 passes is the Sunday 10 PM cron activated.

---

## SOLID and DRY Analysis

**S -- Single Responsibility:** The skill's automated mode extends the existing
classification and parsing responsibility. Git/PR operations and email are
distinct steps added after CSV generation, not mixed into classification logic.

**O -- Open/Closed:** The classification rules are a lookup table. Adding a new
location or skip rule requires adding one row, not modifying branching logic.

**L -- Liskov:** No subtyping introduced. Not applicable.

**I -- Interface Segregation:** The skill's two modes (`interactive`,
`automated`) are invoked with a single `mode` parameter. Callers only supply
what they need.

**D -- Dependency Inversion:** `GITHUB_PAT` and `REPO_PATH` are injected via
env vars at runtime. The skill does not hardcode credentials or repo paths.

**DRY:** The existing location-to-server mapping logic in schedule-parser is
reused directly in automated mode. Classification rules live in one place
(the skill). The email template is defined once and shared between success,
failure, and dry-run paths (subject prefix differs, body structure is the same).

---

## Pre-merge gates (before any PR for this work lands)

- CI green: ruff, mypy, pytest (see `.github/workflows/`)
- Code review approved
- All three testing phases passed and documented in PR description
- PR body links to this spec
