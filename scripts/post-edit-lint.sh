#!/bin/bash
# Post-edit hook: runs ruff linting on edited Python files.
# Reads JSON from stdin (Claude Code hook input format).
# Provides immediate feedback when code style violations are introduced.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

if [[ "$FILE_PATH" == *.py ]]; then
  if command -v python &> /dev/null; then
    if ! python -m ruff check "$FILE_PATH" --quiet 2>/dev/null; then
      echo "Lint warning: $FILE_PATH has style violations. Run 'ruff check --fix .' to auto-fix." >&2
    fi
  fi
fi

exit 0
