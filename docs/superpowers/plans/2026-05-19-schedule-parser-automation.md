# Schedule Parser Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the schedule-parser skill with an `automated` mode that classifies events without user interaction, commits to a branch, opens and merges a PR, and sends an email summary -- triggered every Sunday night via CronCreate.

**Architecture:** Two new Python modules (`classify_events.py`, `format_email.py`) live in `src/schedule_automation/` and are tested like any other module in the project. The existing SKILL.md gains an `Automated mode` section that calls these modules and adds branch/PR/merge/email steps. The skill zip is rebuilt. A CronCreate schedule fires it every Sunday night with `GITHUB_PAT` injected as an env var.

**Tech Stack:** Python 3.11, pytest, zipfile (stdlib), gh CLI, Gmail MCP, git

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `src/schedule_automation/__init__.py` | Create | Package marker |
| `src/schedule_automation/classify_events.py` | Create | Resolve [LOCATION UNKNOWN], apply skip rules |
| `src/schedule_automation/format_email.py` | Create | Format success/failure email bodies |
| `tests/unit/test_classify_events.py` | Create | Unit tests for classify_events |
| `tests/unit/test_format_email.py` | Create | Unit tests for format_email |
| `schedules/schedule-parser/SKILL.md` | Modify (via zip) | Add automated mode section |
| `schedules/schedule-parser.skill` | Rebuild | Updated zip of skill directory |

---

### Task 1: Create src/schedule_automation package

**Files:**
- Create: `src/schedule_automation/__init__.py`

- [ ] **Step 1: Check current branch**

```bash
git branch --show-current
```
Expected: anything other than `main`. If `main`, run:
```bash
git checkout -b feature/schedule-parser-automation
```

- [ ] **Step 2: Create the package marker**

Create `src/schedule_automation/__init__.py` as an empty file.

- [ ] **Step 3: Verify import works**

```bash
python3 -c "import src.schedule_automation; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/schedule_automation/__init__.py
git commit -m "feat: add schedule_automation package"
```

---

### Task 2: Implement classify_events (TDD -- skip rules)

**Files:**
- Create: `src/schedule_automation/classify_events.py`
- Create: `tests/unit/test_classify_events.py`

---

#### Cycle 2a: Skip rules (Choir, Confession, Sunday School, Servants Meeting, Youth)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_classify_events.py`:

```python
import pytest
from src.schedule_automation.classify_events import classify_schedule_text

BULLET = "•"


class TestSkipRules:
    def test_skips_choir_service(self):
        text = f"{BULLET} 5:00 PM - 6:00 PM - Choir Service (St. Mary & St. Joseph)\n"
        result, decisions = classify_schedule_text(text)
        assert "Choir Service" not in result
        assert len(decisions) == 1
        assert decisions[0].outcome == "skipped"
        assert decisions[0].title == "Choir Service"

    def test_skips_confession(self):
        text = f"{BULLET} 8:00 PM - 9:30 PM - Confession (St. Mary & St. Joseph)\n"
        result, decisions = classify_schedule_text(text)
        assert "Confession" not in result
        assert decisions[0].outcome == "skipped"

    def test_skips_sunday_school(self):
        text = f"{BULLET} 11:00 AM - 12:00 PM - Sunday School (St. Mary & St. Joseph)\n"
        result, decisions = classify_schedule_text(text)
        assert "Sunday School" not in result
        assert decisions[0].outcome == "skipped"

    def test_skips_servants_meeting(self):
        text = f"{BULLET} 12:00 PM - 1:00 PM - Servants Meeting (St. Anthony Chapel)\n"
        result, decisions = classify_schedule_text(text)
        assert "Servants Meeting" not in result
        assert decisions[0].outcome == "skipped"

    def test_skips_youth_event(self):
        text = f"{BULLET} 6:00 PM - 8:00 PM - Youth Group (St. Anthony Chapel)\n"
        result, decisions = classify_schedule_text(text)
        assert "Youth Group" not in result
        assert decisions[0].outcome == "skipped"
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_classify_events.py::TestSkipRules -v
```
Expected: `ERROR` -- `cannot import name 'classify_schedule_text'`

- [ ] **Step 3: Write minimal implementation**

Create `src/schedule_automation/classify_events.py`:

```python
import re
import json
import argparse
from typing import NamedTuple

SKIP_KEYWORDS = [
    "Choir",
    "Confession",
    "Sunday School",
    "Servants Meeting",
    "Youth",
]

FALLBACK_LOCATION = "(St. Mary & St. Joseph)"


class Decision(NamedTuple):
    title: str
    outcome: str  # "skipped" | "fallback" | "scheduled"
    reason: str


def _extract_title(line: str) -> str:
    line = line.lstrip("•").strip()
    m = re.match(
        r"[\d:]+\s*(?:AM|PM)\s*-\s*[\d:]+\s*(?:AM|PM)\s*-\s*(.*)",
        line,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip()
        return re.sub(r"\s*[\(\[].*?[\)\]]\s*$", "", raw).strip()
    return line


def _is_skip(title: str) -> bool:
    return any(kw.lower() in title.lower() for kw in SKIP_KEYWORDS)


def _has_unknown_location(line: str) -> bool:
    return "[LOCATION UNKNOWN]" in line


def classify_schedule_text(text: str) -> tuple[str, list[Decision]]:
    decisions: list[Decision] = []
    output_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("•"):
            output_lines.append(line)
            continue

        title = _extract_title(stripped)

        if _is_skip(title):
            decisions.append(Decision(title=title, outcome="skipped", reason="matches skip rule"))
            continue

        if _has_unknown_location(stripped):
            resolved = stripped.replace("[LOCATION UNKNOWN]", FALLBACK_LOCATION)
            output_lines.append(resolved)
            decisions.append(Decision(
                title=title,
                outcome="fallback",
                reason=f"unknown location, defaulted to win-server-1 via {FALLBACK_LOCATION}",
            ))
        else:
            output_lines.append(line)
            decisions.append(Decision(title=title, outcome="scheduled", reason="location known"))

    return "\n".join(output_lines), decisions
```

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_classify_events.py::TestSkipRules -v
```
Expected: `5 passed`

- [ ] **Step 5: Refactor**

Review `_extract_title`: the double strip (`lstrip` + `re.sub`) is needed; names are clear. No duplication or extraction opportunity here. No refactor needed for this cycle.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
python -m pytest tests/unit/ -v
```
Expected: all existing tests pass, 5 new tests pass.

---

#### Cycle 2b: Location resolution

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_classify_events.py`)

```python
class TestLocationResolution:
    def test_resolves_unknown_location_to_win_server(self):
        text = f"{BULLET} 6:30 PM - 7:15 PM - Vespers [LOCATION UNKNOWN]\n"
        result, decisions = classify_schedule_text(text)
        assert "[LOCATION UNKNOWN]" not in result
        assert "(St. Mary & St. Joseph)" in result
        assert decisions[0].outcome == "fallback"
        assert "win-server-1" in decisions[0].reason

    def test_known_location_passes_through_unchanged(self):
        line = f"{BULLET} 5:30 AM - 7:30 AM - Divine Liturgy (St. Mary & St. Joseph)"
        result, decisions = classify_schedule_text(line + "\n")
        assert line in result
        assert decisions[0].outcome == "scheduled"

    def test_non_bullet_lines_pass_through(self):
        text = "Wednesday:\n"
        result, decisions = classify_schedule_text(text)
        assert "Wednesday:" in result
        assert decisions == []
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_classify_events.py::TestLocationResolution -v
```
Expected: `3 failed` -- `classify_schedule_text` exists but location tests fail

- [ ] **Step 3: Implementation already complete** -- the `classify_schedule_text` written in Cycle 2a already handles these cases.

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_classify_events.py::TestLocationResolution -v
```
Expected: `3 passed`

- [ ] **Step 5: Refactor**

`_has_unknown_location` is a one-liner predicate. `_extract_title` is clear. No duplication across cycles. No refactor needed.

---

#### Cycle 2c: Mixed events

- [ ] **Step 1: Add failing test** (append to `tests/unit/test_classify_events.py`)

```python
class TestMixedEvents:
    def test_mixes_skip_and_keep(self):
        text = (
            "Saturday:\n"
            f"{BULLET} 5:00 PM - 6:00 PM - Choir Service (St. Mary & St. Joseph)\n"
            f"{BULLET} 6:00 PM - 6:30 PM - Vespers (St. Mary & St. Joseph)\n"
        )
        result, decisions = classify_schedule_text(text)
        assert "Choir Service" not in result
        assert "Vespers" in result
        assert len(decisions) == 2
        assert decisions[0].outcome == "skipped"
        assert decisions[1].outcome == "scheduled"
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_classify_events.py::TestMixedEvents -v
```
Expected: `1 failed`

- [ ] **Step 3: Already implemented** -- no production code change needed.

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_classify_events.py::TestMixedEvents -v
```
Expected: `1 passed`

- [ ] **Step 5: Refactor**

Three test classes cover distinct concerns (skip rules, location, mixed). No duplication in test setup -- bullet character defined once as `BULLET` at module level. No further refactor needed.

- [ ] **Step 6: Add CLI entry point** to `classify_events.py` (append after `classify_schedule_text`):

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--decisions", required=True)
    args = parser.parse_args()

    with open(args.input) as f:
        text = f.read()

    processed, decisions = classify_schedule_text(text)

    with open(args.output, "w") as f:
        f.write(processed)

    with open(args.decisions, "w") as f:
        json.dump([d._asdict() for d in decisions], f, indent=2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/schedule_automation/classify_events.py tests/unit/test_classify_events.py
git commit -m "feat: add classify_events module with skip and location-resolution rules"
```

---

### Task 3: Implement format_email (TDD)

**Files:**
- Create: `src/schedule_automation/format_email.py`
- Create: `tests/unit/test_format_email.py`

---

#### Cycle 3a: format_success_email

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_format_email.py`:

```python
import pytest
from src.schedule_automation.format_email import format_success_email, format_failure_email

CSV_CONTENT = (
    "server_id,date,start_time,stop_time,action,timezone,title\n"
    "win-server-1,2026-05-20,18:25,19:30,streaming,America/New_York,Vespers\n"
)


@pytest.fixture
def csv_file(tmp_path):
    p = tmp_path / "current_week.csv"
    p.write_text(CSV_CONTENT)
    return str(p)


class TestFormatSuccessEmail:
    def test_subject_contains_week_label(self, csv_file):
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=[],
            pr_url="https://github.com/wfhanna1/Automated-obs-trigger/pull/1",
        )
        assert "May 18 - 24, 2026" in result["subject"]
        assert "Schedule loaded" in result["subject"]

    def test_body_contains_event_from_csv(self, csv_file):
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=[],
            pr_url="https://github.com/wfhanna1/Automated-obs-trigger/pull/1",
        )
        assert "Vespers" in result["body"]
        assert "win-server-1" in result["body"]

    def test_pr_url_in_body(self, csv_file):
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=[],
            pr_url="https://github.com/wfhanna1/Automated-obs-trigger/pull/42",
        )
        assert "pull/42" in result["body"]
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_format_email.py::TestFormatSuccessEmail -v
```
Expected: `ERROR` -- `cannot import name 'format_success_email'`

- [ ] **Step 3: Write minimal implementation**

Create `src/schedule_automation/format_email.py`:

```python
import csv
import json
import argparse


def _format_csv_table(csv_path: str) -> str:
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                f"{row['server_id']:<16}{row['date']}  {row['start_time']}  {row['stop_time']}  {row['title']}"
            )
    header = f"{'Server':<16}{'Date':<12}Start  Stop   Title"
    return header + "\n" + "\n".join(rows)


def _format_decisions(decisions: list[dict]) -> str:
    notable = [d for d in decisions if d["outcome"] in ("skipped", "fallback", "excluded")]
    if not notable:
        return "(none)"
    return "\n".join(f"- {d['title']}: {d['outcome']} -- {d['reason']}" for d in notable)


def format_success_email(
    week_label: str,
    csv_path: str,
    decisions: list[dict],
    pr_url: str,
    dry_run: bool = False,
) -> dict[str, str]:
    prefix = "[DRY RUN] " if dry_run else ""
    return {
        "subject": f"{prefix}Schedule loaded: {week_label}",
        "body": (
            f"Week of {week_label}\n\n"
            f"SCHEDULED EVENTS\n{_format_csv_table(csv_path)}\n\n"
            f"DECISIONS I MADE\n{_format_decisions(decisions)}\n\n"
            f"PR: {pr_url}"
        ),
    }


def format_failure_email(week_label: str, failed_step: str, error: str) -> dict[str, str]:
    return {
        "subject": f"[FAILED] Schedule automation: {week_label}",
        "body": (
            f"Schedule automation failed for {week_label}.\n\n"
            f"Failed at: {failed_step}\n"
            f"Error: {error}\n\n"
            f"Manual intervention required."
        ),
    }
```

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_format_email.py::TestFormatSuccessEmail -v
```
Expected: `3 passed`

- [ ] **Step 5: Refactor**

`_format_csv_table` and `_format_decisions` are private helpers with single purposes. `format_success_email` and `format_failure_email` are public and distinct. No duplication. No refactor needed.

---

#### Cycle 3b: Dry run and decisions

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_format_email.py`)

```python
    def test_dry_run_adds_prefix_to_subject(self, csv_file):
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=[],
            pr_url="(dry run)",
            dry_run=True,
        )
        assert result["subject"].startswith("[DRY RUN]")

    def test_fallback_decision_appears_in_body(self, csv_file):
        decisions = [
            {"title": "Vespers", "outcome": "fallback",
             "reason": "unknown location, defaulted to win-server-1"},
        ]
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=decisions,
            pr_url="https://github.com/wfhanna1/Automated-obs-trigger/pull/1",
        )
        assert "DECISIONS I MADE" in result["body"]
        assert "fallback" in result["body"]

    def test_scheduled_decisions_show_none(self, csv_file):
        decisions = [{"title": "Vespers", "outcome": "scheduled", "reason": "location known"}]
        result = format_success_email(
            week_label="May 18 - 24, 2026",
            csv_path=csv_file,
            decisions=decisions,
            pr_url="https://github.com/wfhanna1/Automated-obs-trigger/pull/1",
        )
        assert "(none)" in result["body"]
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_format_email.py -k "dry_run or decision" -v
```
Expected: `3 failed`

- [ ] **Step 3: Implementation already complete** -- `format_success_email` handles `dry_run` and `_format_decisions` filters on outcome. No code change needed.

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_format_email.py -k "dry_run or decision" -v
```
Expected: `3 passed`

- [ ] **Step 5: Refactor**

`_format_decisions` filters `["skipped", "fallback", "excluded"]` -- this list is the definition of "notable." It could become a constant `NOTABLE_OUTCOMES` but with only 3 values it's not worth extracting yet. No refactor needed.

---

#### Cycle 3c: format_failure_email

- [ ] **Step 1: Add failing tests** (append to `tests/unit/test_format_email.py`)

```python
class TestFormatFailureEmail:
    def test_subject_contains_failed_marker_and_week(self):
        result = format_failure_email(
            week_label="May 18 - 24, 2026",
            failed_step="git push",
            error="Authentication failed",
        )
        assert "[FAILED]" in result["subject"]
        assert "May 18 - 24, 2026" in result["subject"]

    def test_body_contains_step_and_error(self):
        result = format_failure_email(
            week_label="May 18 - 24, 2026",
            failed_step="git push",
            error="Authentication failed",
        )
        assert "git push" in result["body"]
        assert "Authentication failed" in result["body"]
```

- [ ] **Step 2: Run -- verify RED**

```bash
python -m pytest tests/unit/test_format_email.py::TestFormatFailureEmail -v
```
Expected: `2 failed` -- `format_failure_email` is imported (already in the import line from Cycle 3a) but the function is not yet implemented.

- [ ] **Step 3: `format_failure_email` already implemented** in Task 3 Step 3. No code change needed.

- [ ] **Step 4: Run -- verify GREEN**

```bash
python -m pytest tests/unit/test_format_email.py::TestFormatFailureEmail -v
```
Expected: `2 passed`

- [ ] **Step 5: Refactor**

`format_failure_email` and `format_success_email` share no logic. Both produce `{"subject", "body"}` dicts -- the dict structure is the implicit interface. No duplication worth extracting at this point.

- [ ] **Step 6: Add CLI entry point** (append to `format_email.py`)

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--week-label", required=True)
    parser.add_argument("--pr-url", default="(PR not created -- dry run)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.decisions) as f:
        decisions = json.load(f)

    result = format_success_email(
        week_label=args.week_label,
        csv_path=args.csv,
        decisions=decisions,
        pr_url=args.pr_url,
        dry_run=args.dry_run,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/unit/ -v
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/schedule_automation/format_email.py tests/unit/test_format_email.py
git commit -m "feat: add format_email module for schedule automation notifications"
```

---

### Task 4: Update SKILL.md with automated mode

**Files:**
- Modify: `/tmp/skill-extract/schedule-parser/SKILL.md`
- Rebuild: `schedules/schedule-parser.skill`

- [ ] **Step 1: Extract current skill**

```bash
cd /tmp && rm -rf skill-extract && mkdir skill-extract && cd skill-extract
python3 -c "
import zipfile, io
with open('/Users/wasimhanna/Code/Automated-obs-trigger/schedules/schedule-parser.skill', 'rb') as f:
    z = zipfile.ZipFile(io.BytesIO(f.read()))
    z.extractall('.')
print('extracted')
"
```

- [ ] **Step 2: Append automated mode section to SKILL.md**

Open `/tmp/skill-extract/schedule-parser/SKILL.md` and append the following at the end (after the CSV format reference section):

```markdown
---

## Automated mode

Triggered when the skill is invoked with `mode=automated` or `mode=automated --dry-run`.

In automated mode:
- Never ask the user questions. Apply all classification rules silently.
- Log every decision made (skip, fallback, scheduled) for inclusion in the email.
- After the CSV is written, execute the git/PR/merge/email steps below.
- In `--dry-run`, skip push/PR/merge but still send the email with `[DRY RUN]` subject.

### Automated step 3 (replaces interactive step 3)

After running `parse_gcal.py`, instead of asking about `[LOCATION UNKNOWN]` events:

```bash
python3 <repo_root>/src/schedule_automation/classify_events.py \
  --input /tmp/schedule_input.txt \
  --output /tmp/schedule_classified.txt \
  --decisions /tmp/classification_decisions.json
```

Use `/tmp/schedule_classified.txt` as input for steps 4-6.

### Automated step 4 (replaces interactive step 4)

Run the preview but do not ask for confirmation. Print the preview table to the
conversation for the audit log and continue immediately.

### Automated step 7 (replaces interactive step 7)

**1. Clear any stale git lock files:**
```bash
[ -f <repo_root>/.git/index.lock ] && rm <repo_root>/.git/index.lock
[ -f <repo_root>/.git/HEAD.lock ] && rm <repo_root>/.git/HEAD.lock
```

**2. Create branch and commit:**
```bash
BRANCH="chore/schedule-<MONDAY_ISO>"
git -C <repo_root> checkout main
git -C <repo_root> pull origin main
git -C <repo_root> checkout -b $BRANCH

LAST_DATE=$(grep -v '^server_id' <schedules_dir>/current_week.csv | grep -v '^$' \
  | awk -F',' '{print $2}' | sort | tail -1)
mv <schedules_dir>/current_week.csv <schedules_dir>/current_week_${LAST_DATE}.csv

git -C <repo_root> add schedules/
git -C <repo_root> commit -m "Schedule update: week of <MONDAY_ISO>"
```

**3. Push branch and create/merge PR** (skip these three blocks in `--dry-run`):
```bash
git -C <repo_root> remote set-url origin \
  https://${GITHUB_PAT}@github.com/wfhanna1/Automated-obs-trigger.git
git -C <repo_root> push origin $BRANCH
```
```bash
gh auth login --with-token <<< ${GITHUB_PAT}
PR_URL=$(gh pr create \
  --title "Schedule update: week of <MONDAY_ISO>" \
  --body "Automated weekly schedule update.

$(cat <schedules_dir>/current_week.csv)

Generated by schedule-parser automated mode." \
  --base main --head $BRANCH)
```
```bash
gh pr merge $BRANCH --merge --delete-branch
```

In `--dry-run`, print each of the three blocks above instead of executing them.
Set `PR_URL="(dry run -- PR not created)"`.

**4. Format and send email notification:**

```bash
EMAIL_JSON=$(python3 <repo_root>/src/schedule_automation/format_email.py \
  --csv <schedules_dir>/current_week.csv \
  --decisions /tmp/classification_decisions.json \
  --week-label "<WEEK_LABEL>" \
  --pr-url "$PR_URL" \
  [--dry-run])
```

Extract `subject` and `body` from `$EMAIL_JSON` and use Gmail MCP
`mcp__claude_ai_Gmail__create_draft` to create a draft addressed to
`wasim.hanna@pm.me`. The draft will appear in Gmail for review.

If any step fails before the email is sent, run:
```bash
python3 -c "
import json, sys
sys.path.insert(0, '<repo_root>')
from src.schedule_automation.format_email import format_failure_email
print(json.dumps(format_failure_email('<WEEK_LABEL>', '<failed_step>', '<error_message>')))
"
```
And create a failure draft email with the result.
```

- [ ] **Step 3: Rebuild the skill zip**

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

- [ ] **Step 4: Verify rebuild**

```bash
python3 -c "
import zipfile
with zipfile.ZipFile('/Users/wasimhanna/Code/Automated-obs-trigger/schedules/schedule-parser.skill') as z:
    print(z.namelist())
"
```
Expected: `['schedule-parser/', 'schedule-parser/SKILL.md', 'schedule-parser/scripts/', 'schedule-parser/scripts/parse_schedule.py', 'schedule-parser/scripts/parse_gcal.py']`

- [ ] **Step 5: Run quality gates**

```bash
python -m pytest tests/unit/ -v
python -m ruff check .
python -m mypy .
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add schedules/schedule-parser.skill src/schedule_automation/
git commit -m "feat: extend schedule-parser with automated mode (git/PR/email)"
```

---

### Task 5: Phase 1 -- Local dry run

This is a manual validation task. No code changes expected.

- [ ] **Step 1: Run the skill in automated dry-run mode**

In Claude Code, invoke:
```
Run the schedule-parser skill in automated --dry-run mode
```

- [ ] **Step 2: Verify the following in the output**

- Calendar fetch completes via browser
- Preview table is printed without asking for confirmation
- `classify_events.py` is called and `/tmp/classification_decisions.json` is written
- Git commands are printed but not executed (dry-run)
- `format_email.py` is called and produces a JSON email payload
- Gmail draft is created with subject starting `[DRY RUN] Schedule loaded:`
- No errors

- [ ] **Step 3: Open Gmail and verify the draft arrived**

Check Gmail drafts folder for a message addressed to `wasim.hanna@pm.me` with:
- Subject: `[DRY RUN] Schedule loaded: week of ...`
- Body contains: scheduled events table, DECISIONS I MADE section, `(dry run)` PR line

If the draft is not there, check the Claude conversation for Gmail MCP errors and resolve before proceeding to Phase 2.

---

### Task 6: Register cloud schedule + Phase 2 dry run

- [ ] **Step 1: Push the feature branch**

```bash
git push origin feature/schedule-parser-automation
```

Open a PR and merge it to main.

- [ ] **Step 2: Generate a GitHub PAT**

In GitHub: Settings → Developer settings → Personal access tokens → Fine-grained tokens.
- Repository: `wfhanna1/Automated-obs-trigger`
- Permissions: Contents (read/write), Pull requests (read/write)
- Copy the token value.

- [ ] **Step 3: Register the CronCreate schedule**

Run `/schedule` in Claude Code. Configure:

| Field | Value |
|---|---|
| Name | `weekly-schedule-automation` |
| Cron | `0 22 * * 0` (Sunday 10 PM ET) |
| Prompt | `Run the schedule-parser skill in automated mode` |
| Env var | `GITHUB_PAT=<your-PAT>` |

- [ ] **Step 4: Manually trigger a dry run from the cloud schedule**

In the schedule management UI (or via `/schedule run weekly-schedule-automation --dry-run`), trigger a manual execution with `--dry-run`.

- [ ] **Step 5: Verify Phase 2 pass criteria**

- Browser access works from cloud agent (calendar fetched)
- Gmail MCP accessible (draft created)
- `GITHUB_PAT` env var is readable by the agent
- `gh` CLI authenticates successfully with the PAT
- `[DRY RUN]` email draft received

If any check fails, resolve before Phase 3.

---

### Task 7: Phase 3 -- Cloud live run

- [ ] **Step 1: Manually trigger a live run from the cloud schedule**

Trigger the schedule without `--dry-run`. This is the first live end-to-end execution.

- [ ] **Step 2: Verify Phase 3 pass criteria**

- `schedules/current_week.csv` is updated in the repo
- PR `chore/schedule-<date>` is created and merged to main
- GitHub Action `load-schedule.yml` fires on the merge (check Actions tab)
- LoadSchedule Azure Function returns HTTP 200 (check Action log)
- Summary email draft received with PR link

- [ ] **Step 3: Activate the Sunday night cron**

Once Phase 3 passes, confirm the schedule is active. No further changes needed -- it fires every Sunday at 10 PM ET automatically.
