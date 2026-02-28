#!/bin/bash
# Task completion gate hook.
# Runs when an agent team task is being marked complete.
# Exits with code 2 to prevent completion if quality gates fail.
#
# Reads gate commands from .claude/quality-gates.json.

CONFIG_FILE=".claude/quality-gates.json"
FAILURES=""

if [ -f "$CONFIG_FILE" ]; then
  TYPECHECK_CMD=$(jq -r '.typecheck.command // empty' "$CONFIG_FILE")
  TYPECHECK_MSG=$(jq -r '.typecheck.failureMessage // "Type checking failed"' "$CONFIG_FILE")
  LINT_CMD=$(jq -r '.lint.command // empty' "$CONFIG_FILE")
  LINT_MSG=$(jq -r '.lint.failureMessage // "Lint checks failed"' "$CONFIG_FILE")
  TEST_CMD=$(jq -r '.test.command // empty' "$CONFIG_FILE")
  TEST_MSG=$(jq -r '.test.failureMessage // "Tests failed"' "$CONFIG_FILE")

  if [ -n "$TYPECHECK_CMD" ]; then
    if ! eval "$TYPECHECK_CMD" > /dev/null 2>&1; then
      FAILURES="${FAILURES}\n- ${TYPECHECK_MSG}"
    fi
  fi

  if [ -n "$LINT_CMD" ]; then
    if ! eval "$LINT_CMD" > /dev/null 2>&1; then
      FAILURES="${FAILURES}\n- ${LINT_MSG}"
    fi
  fi

  if [ -n "$TEST_CMD" ]; then
    if ! eval "$TEST_CMD" > /dev/null 2>&1; then
      FAILURES="${FAILURES}\n- ${TEST_MSG}"
    fi
  fi
else
  exit 0
fi

if [ -n "$FAILURES" ]; then
  echo "Task completion blocked. Quality gates failed:" >&2
  echo -e "$FAILURES" >&2
  echo "" >&2
  echo "Fix the issues above before marking this task complete." >&2
  exit 2
fi

exit 0
