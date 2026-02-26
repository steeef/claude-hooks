# git-hooks

Git safety hooks for Claude Code that enforce branch workflow, block dangerous
commands, and suggest worktrees for feature work.

## Hooks

### PreToolUse: git_pre_hook.py

Unified entry point that runs all git safety checks:

1. **git_add_block** - Blocks dangerous git add patterns (wildcards, -A, .)
2. **git_checkout_safety** - Warns about checkout commands that could lose work
3. **git_branch_workflow** - Enforces Jira-prefixed branch naming and blocks
   commits on main/master
4. **worktree_suggestion** - Suggests using git worktrees for feature branches

### PostToolUse: cleanup_hook.py

Detects PR merges and provides worktree cleanup instructions.

## Configuration

### Protected Branch Allowlist

By default, commits on `main`/`master` are blocked. To allow direct commits in
specific repos (e.g., documentation-only repos), add them to
`~/.config/claude-hooks/config.json`:

```json
{
  "protected_branch_allowlist": [
    "~/code/work/thoughts"
  ]
}
```

Paths support `~` expansion. Matched against the repo root
(`git rev-parse --show-toplevel`). Allowlisted repos get an approval prompt
instead of a hard block.
