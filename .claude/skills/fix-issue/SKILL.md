---
name: fix-issue
description: Fix a GitHub issue end-to-end using the agent team workflow
disable-model-invocation: true
---

Analyze and fix the GitHub issue: $ARGUMENTS

Follow this workflow:

1. **Understand the issue**
   - Run `gh issue view $ARGUMENTS` to get issue details
   - Identify the type: bug, feature, or improvement
   - Identify affected areas: Azure Functions code, infrastructure, tests, or cross-cutting

2. **Plan the fix**
   - Search the codebase for relevant files
   - Identify root cause (for bugs) or implementation approach (for features)
   - Write a brief plan: what changes, which files, what tests
   - Message the Tech Lead with the plan before proceeding

3. **Implement the fix**
   - Follow file ownership rules from CLAUDE.md
   - Apply clean code standards and 12-factor principles
   - Make the minimum change needed to resolve the issue

4. **Test the fix**
   - Write tests that reproduce the issue (for bugs) or validate the feature
   - Run `python -m pytest` to ensure all tests pass
   - Run `python -m ruff check .` and `python -m mypy .`

5. **Review the fix**
   - Message the code-reviewer agent to review changes
   - Message the security-reviewer agent for security-sensitive changes (SSH, Key Vault, env vars)
   - Address any feedback

6. **Ship it**
   - Create a descriptive commit message referencing the issue number
   - Push and create a PR with `gh pr create`
   - Link the PR to the issue
