---
name: tdd
description: Test-driven development workflow. Write failing tests first, then implement to make them pass.
disable-model-invocation: true
---

Implement the following feature using Test-Driven Development: $ARGUMENTS

Follow the strict Red-Green-Refactor cycle:

## Phase 1: RED - Write Failing Tests

1. Analyze the feature requirements
2. Break the feature into testable behaviors
3. Message the qa-engineer agent to write tests in `tests/unit/` or `tests/integration/` that:
   - Cover the happy path
   - Cover edge cases and error conditions
   - Mock external dependencies (SSH, WebSocket, Azure SDK, HTTP)
   - Follow Arrange-Act-Assert pattern
   - Use descriptive names (`test_<module>_<behavior>_when_<condition>`)
4. Run `python -m pytest` to verify tests FAIL for the right reasons

## Phase 2: GREEN - Implement Minimum Code

1. Identify which agent should implement (backend-engineer or platform-engineer)
2. Implement the MINIMUM code to make all tests pass
3. Do NOT over-engineer. Just make the tests green.
4. Run `python -m pytest` to verify ALL tests pass
5. Run `python -m ruff check .` and `python -m mypy .` — fix any issues

## Phase 3: REFACTOR - Clean Up

1. Review the implementation for clean code improvements
2. Message the code-reviewer agent to identify improvements
3. Refactor while keeping all tests green
4. Run `python -m pytest` after each refactoring step

## Completion

- All tests pass
- Code is clean and follows project standards
- `ruff check .` passes
- `mypy .` passes
- Commit with a descriptive message
