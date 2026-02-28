---
name: code-review
description: Run a comprehensive code review on recent changes using the code-reviewer and security-reviewer agents
disable-model-invocation: true
---

Run a comprehensive code review on the recent changes: $ARGUMENTS

1. **Gather context**
   - Run `git diff` to see all changes (or `git diff $ARGUMENTS` if a branch/commit is specified)
   - Identify all changed files and their ownership domains

2. **Code quality review**
   - Message the code-reviewer agent to analyze changes for:
     - Clean code compliance (naming, functions, SOLID)
     - 12-factor compliance (config, statelessness, logs)
     - Module boundary adherence (function_app orchestrates, src/ modules are independent)
     - Type annotation completeness
     - Test coverage

3. **Security review**
   - Message the security-reviewer agent to check for:
     - SSH key handling and tempfile cleanup
     - Secrets in log statements
     - OWASP Top 10 vulnerabilities
     - Dependency vulnerabilities (`pip-audit`)
     - Service Bus message validation

4. **Synthesize findings**
   - Combine both reviews into a single report
   - Prioritize: Critical > High > Medium > Low
   - For each finding, include the file, line, issue, and remediation

5. **Report results**
   - If reviewing a PR, post the review as a comment with `gh pr review`
   - If reviewing local changes, output the report directly
