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

No configuration required. The hooks are automatically loaded by Claude Code
when `CLAUDE_HOOKS_DIR` points to the parent claude-hooks directory.
