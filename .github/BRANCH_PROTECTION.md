# Repository Rulesets

This repository uses **Rulesets** (the modern replacement for branch protection rules).

View and manage rulesets at: **Settings → Rules → Rulesets**

## Main Branch Protection Ruleset

**Target:** `refs/heads/main`
**Enforcement:** Active

### Rules Applied

| Rule | Configuration |
|------|---------------|
| **Pull Request Required** | ✅ Enabled |
| **Required Approvals** | 1 |
| **Dismiss Stale Reviews** | ✅ On push |
| **Require Code Owner Review** | ✅ Enabled |
| **Require Conversation Resolution** | ✅ Enabled |
| **Required Status Checks** | Strict mode |
| **Prevent Deletion** | ✅ Enabled |
| **Prevent Force Push** | ✅ Enabled |

### Required Status Checks

The following CI jobs must pass before merging:

- `Lint` - Ruff linter and formatter
- `Type Check` - mypy type checking
- `Test` - pytest test suite
- `Security Audit` - pip-audit security scan

### Bypass Actors

No bypass actors configured - rules apply to everyone including administrators.

## Why Rulesets over Branch Protection?

Rulesets provide:
- **Better organization** - Multiple rulesets with different targets
- **More granular control** - Fine-tuned rules per pattern
- **Easier management** - UI and API improvements
- **Future-proof** - GitHub's recommended approach going forward

## Notes

- The release workflow uses `actions/github-script` to auto-merge Release PRs
- If rulesets block auto-merge, configure bypass actors for the release bot
- Or manually merge Release PRs when they're created

