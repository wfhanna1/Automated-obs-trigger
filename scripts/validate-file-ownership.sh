#!/bin/bash
# Pre-edit hook: validates file ownership boundaries.
# Reads JSON from stdin (Claude Code hook input format).
# Exits with code 2 to block edits that violate ownership rules.
#
# Ownership boundaries (from CLAUDE.md):
#   backend-engineer:  function_app.py, src/
#   platform-engineer: infra/, .github/, host.json, requirements.txt
#   qa-engineer:       tests/
#   security-reviewer: read-only
#   code-reviewer:     read-only

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

AGENT_TYPE="${CLAUDE_AGENT_TYPE:-}"

if [ -z "$AGENT_TYPE" ]; then
  exit 0
fi

case "$AGENT_TYPE" in
  backend-engineer)
    if echo "$FILE_PATH" | grep -qE "infra/|\.github/|host\.json|requirements\.txt"; then
      echo "Blocked: backend-engineer cannot modify infra/, .github/, host.json, or requirements.txt (owned by platform-engineer)" >&2
      exit 2
    fi
    ;;
  platform-engineer)
    if echo "$FILE_PATH" | grep -qE "^function_app\.py$|src/"; then
      echo "Blocked: platform-engineer cannot modify function_app.py or src/ (owned by backend-engineer)" >&2
      exit 2
    fi
    ;;
  qa-engineer)
    if echo "$FILE_PATH" | grep -qE "^function_app\.py$|^src/|^infra/|^\.github/"; then
      echo "Blocked: qa-engineer cannot modify source or infrastructure files (owned by backend/platform engineers)" >&2
      exit 2
    fi
    ;;
  security-reviewer|code-reviewer)
    echo "Blocked: $AGENT_TYPE is read-only and cannot modify files" >&2
    exit 2
    ;;
esac

exit 0
