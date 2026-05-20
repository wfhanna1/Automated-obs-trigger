# Schedule Parser Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the schedule-parser skill with an `automated` mode that runs every Sunday night via CronCreate, classifies events without user interaction, creates and merges a PR, and sends an email summary.

**Architecture:** All logic lives in SKILL.md inside the existing skill zip. Claude applies classification rules directly, runs git/gh bash commands, and formats the email via Gmail MCP. No new Python files. The skill is rebuilt and a CronCreate schedule fires it weekly.

**Tech Stack:** SKILL.md instructions, bash, gh CLI, Gmail MCP, zipfile (stdlib for rebuild)

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `schedules/schedule-parser/SKILL.md` | Modify (via zip) | Add automated mode section |
| `schedules/schedule-parser.skill` | Rebuild | Updated zip |

---

### Task 1: Update SKILL.md and rebuild the skill zip

**Files:**
- Modify: `/tmp/skill-extract/schedule-parser/SKILL.md`
- Rebuild: `schedules/schedule-parser.skill`

- [ ] **Step 1: Check current branch**

```bash
git branch --show-current
```
Expected: `feature/schedule-parser-automation`. If on `main`, run:
```bash
git checkout feature/schedule-parser-automation
```

- [ ] **Step 2: Extract the current skill zip**

```bash
cd /tmp && rm -rf skill-extract && mkdir skill-extract && cd skill-extract
python3 -c "
import zipfile, io
with open('/Users/wasimhanna/Code/Automated-obs-trigger/schedules/schedule-parser.skill', 'rb') as f:
    z = zipfile.ZipFile(io.BytesIO(f.read()))
    z.extractall('.')
print('extracted:', z.namelist())
"
```

- [ ] **Step 3: Append the automated mode section to SKILL.md**

Open `/tmp/skill-extract/schedule-parser/SKILL.md` and append the following after the last line:

```
---

## Automated mode

Triggered when invoked with `mode=automated` or `mode=automated --dry-run`.

**Rules -- never ask the user:**
- Apply skip rules silently. Remove any line from `/tmp/schedule_input.txt` whose
  event title contains: Choir, Confession, Sunday School, Servants Meeting, Youth.
- Resolve `[LOCATION UNKNOWN]` silently. Replace it with `(St. Mary & St. Joseph)`.
  This defaults the event to win-server-1 via the existing server mapping.
- Log every decision (skipped title, resolved location) for inclusion in the email.

**Dry-run flag:** When `--dry-run` is set, skip the push/PR/merge commands.
Print what would have been run instead. Still send the email with `[DRY RUN]`
in the subject so email delivery can be validated.

### Automated step 3 (replaces interactive step 3)

After `parse_gcal.py` writes `/tmp/schedule_input.txt`, apply the rules above
directly -- edit the file to remove skip-rule lines and replace `[LOCATION UNKNOWN]`
tags. Keep a log of every change made.

### Automated step 4 (replaces interactive step 4)

Run the preview as normal but do not wait for confirmation. Print the table to
the conversation and continue immediately.

### Automated step 7 (replaces interactive step 7)

**1. Clear stale git lock files (always run this first):**
```
[ -f <repo_root>/.git/index.lock ] && rm <repo_root>/.git/index.lock
[ -f <repo_root>/.git/HEAD.lock ]  && rm <repo_root>/.git/HEAD.lock
```

**2. Create branch and commit:**
```
BRANCH="chore/schedule-<MONDAY_ISO>"
git -C <repo_root> checkout main
git -C <repo_root> pull origin main
git -C <repo_root> checkout -b $BRANCH

LAST_DATE=$(grep -v '^server_id' <schedules_dir>/current_week.csv \
  | grep -v '^$' | awk -F',' '{print $2}' | sort | tail -1)
mv <schedules_dir>/current_week.csv \
   <schedules_dir>/current_week_${LAST_DATE}.csv

git -C <repo_root> add schedules/
git -C <repo_root> commit -m "Schedule update: week of <MONDAY_ISO>"
```

**3. Push and open PR** (skip in `--dry-run`, print commands instead):
```
git -C <repo_root> remote set-url origin \
  https://${GITHUB_PAT}@github.com/wfhanna1/Automated-obs-trigger.git
git -C <repo_root> push origin $BRANCH

gh auth login --with-token <<< ${GITHUB_PAT}
PR_URL=$(gh pr create \
  --title "Schedule update: week of <MONDAY_ISO>" \
  --body "Automated weekly schedule update for week of <MONDAY_ISO>." \
  --base main --head $BRANCH)
```

**4. Merge PR** (skip in `--dry-run`):
```
gh pr merge $BRANCH --merge --delete-branch
```

**5. Send email via Gmail MCP:**

Compose a `create_draft` call addressed to `wasim.hanna@pm.me` with:

Subject (normal run):  `Schedule loaded: week of <WEEK_LABEL>`
Subject (dry run):     `[DRY RUN] Schedule loaded: week of <WEEK_LABEL>`

Body:
```
Week of <WEEK_LABEL>

SCHEDULED EVENTS
<table of server_id, date, start_time, stop_time, title from current_week.csv>

DECISIONS I MADE
<bulleted list of every skip and location-resolution decision logged above>
<"(none)" if no decisions were made>

PR: <PR_URL or "(dry run -- PR not created)">
```

If any step fails before the email is created, send a failure draft instead:

Subject: `[FAILED] Schedule automation: week of <WEEK_LABEL>`
Body:
```
Schedule automation failed for <WEEK_LABEL>.

Failed at: <step name>
Error: <error message>

Manual intervention required.
```
```

- [ ] **Step 4: Rebuild the skill zip**

```bash
cd /tmp/skill-extract
python3 -c "
import zipfile, os
with zipfile.ZipFile(
    '/Users/wasimhanna/Code/Automated-obs-trigger/schedules/schedule-parser.skill',
    'w',
    compression=zipfile.ZIP_DEFLATED
) as zf:
    for root, dirs, files in os.walk('schedule-parser'):
        for file in files:
            path = os.path.join(root, file)
            zf.write(path)
print('rebuilt')
"
```

- [ ] **Step 5: Verify the zip contains the updated SKILL.md**

```bash
python3 -c "
import zipfile
with zipfile.ZipFile('/Users/wasimhanna/Code/Automated-obs-trigger/schedules/schedule-parser.skill') as z:
    print(z.namelist())
    print(z.read('schedule-parser/SKILL.md').decode()[-500:])
"
```
Expected: last 500 chars of SKILL.md contain `Automated mode`.

- [ ] **Step 6: Commit**

```bash
git -C /Users/wasimhanna/Code/Automated-obs-trigger add schedules/schedule-parser.skill
git -C /Users/wasimhanna/Code/Automated-obs-trigger commit -m "feat: extend schedule-parser with automated mode"
```

---

### Task 2: Phase 1 -- Local dry run

Manual validation. No code changes.

- [ ] **Step 1: Run the skill in dry-run mode**

In Claude Code, invoke:
```
Run the schedule-parser skill in automated --dry-run mode
```

- [ ] **Step 2: Verify output**

- Calendar fetched via browser without prompting
- Skip-rule events removed silently (confirmed in log)
- `[LOCATION UNKNOWN]` events resolved silently (confirmed in log)
- Preview table printed without asking for confirmation
- Git commands printed but not executed
- Gmail draft created with subject `[DRY RUN] Schedule loaded: week of ...`
- Draft body contains event table and DECISIONS I MADE section

- [ ] **Step 3: Open Gmail and confirm the draft**

Check Gmail drafts for the `[DRY RUN]` message. If missing, check for Gmail MCP
errors in the conversation and fix before proceeding to Phase 2.

---

### Task 3: Register cloud schedule + Phase 2 dry run

- [ ] **Step 1: Push the branch and open a PR**

```bash
git -C /Users/wasimhanna/Code/Automated-obs-trigger push origin feature/schedule-parser-automation
```
Then open a PR from `feature/schedule-parser-automation` into `main` and merge it.

- [ ] **Step 2: Generate a GitHub PAT**

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.
- Repository: `wfhanna1/Automated-obs-trigger`
- Permissions: Contents (read/write), Pull requests (read/write)
- Copy the token.

- [ ] **Step 3: Register the schedule via `/schedule`**

Run `/schedule` and configure:

| Field | Value |
|---|---|
| Name | `weekly-schedule-automation` |
| Cron | `0 22 * * 0` (Sunday 10 PM ET) |
| Prompt | `Run the schedule-parser skill in automated --dry-run mode` |
| Env var | `GITHUB_PAT=<token>` |

- [ ] **Step 4: Manually trigger and verify Phase 2**

Trigger the schedule manually. Confirm:
- Browser access works from cloud
- Gmail MCP accessible from cloud
- `GITHUB_PAT` readable by the agent
- `gh` authenticates with the PAT
- `[DRY RUN]` email draft received

---

### Task 4: Phase 3 -- Cloud live run

- [ ] **Step 1: Update schedule prompt to remove `--dry-run`**

Edit the schedule via `/schedule` to change the prompt to:
```
Run the schedule-parser skill in automated mode
```

- [ ] **Step 2: Manually trigger one live run**

- [ ] **Step 3: Verify end-to-end**

- `current_week.csv` updated in the repo
- PR created and merged to main
- GitHub Action `load-schedule.yml` fires (check Actions tab)
- LoadSchedule Azure Function returns HTTP 200
- Summary email draft received with PR link

- [ ] **Step 4: Confirm schedule is active**

The cron fires every Sunday at 10 PM ET automatically from this point.
No further setup needed.
