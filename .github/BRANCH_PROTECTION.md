# Recommended Branch Protection Rules

Configure these settings in **Settings → Branches → Add branch protection rule** for the `main` branch.

## Branch name pattern

```
main
```

## Protect matching branches

### ✅ Recommended Settings

| Setting | Value | Description |
|---------|-------|-------------|
| **Require a pull request before merging** | ✅ Enabled | All changes must go through PRs |
| **Require approvals** | 1 | At least one approval required |
| **Dismiss stale pull request approvals** | ✅ Enabled | New commits invalidate approvals |
| **Require status checks to pass** | ✅ Enabled | CI must pass before merge |
| **Require branches to be up to date** | ✅ Enabled | Branch must be current with main |
| **Require conversation resolution** | ✅ Enabled | All comments must be resolved |
| **Require signed commits** | Optional | For enhanced security |
| **Include administrators** | ✅ Enabled | Rules apply to everyone |

### Required Status Checks

Add these status checks as required:

- `Lint`
- `Type Check`
- `Test`
- `Security Audit`
- `CodeQL Analysis`

## Notes

- The release workflow uses `actions/github-script` to auto-merge Release PRs
- If branch protection blocks auto-merge, you may need to use a PAT with bypass permissions
- Or manually merge Release PRs when they're created

