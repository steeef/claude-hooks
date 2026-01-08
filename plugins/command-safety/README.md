# command-safety

Command safety hooks for Claude Code that protect against accidental deletions
and destructive infrastructure commands.

## Hooks

### PreToolUse: command_hook.py

Unified entry point that runs all command safety checks:

1. **rm_check** - Blocks rm for tracked files, allows git-ignored files
2. **kubectl_check** - Blocks destructive kubectl commands (delete, apply, etc.)
3. **terraform_check** - Blocks destructive terraform commands (apply, destroy)

## rm Behavior

The rm hook has special handling for git repositories:

- **Inside git repo**: rm is allowed ONLY for git-ignored files (e.g., .DS_Store,
  node_modules/, *.tmp)
- **Outside git repo**: rm is always blocked
- **Mixed targets**: If any target is tracked/non-ignored, the entire command
  is blocked

For tracked files, use `mv` to move to a TRASH/ directory instead.

## Configuration

No configuration required. The hooks are automatically loaded by Claude Code
when `CLAUDE_HOOKS_DIR` points to the parent claude-hooks directory.
