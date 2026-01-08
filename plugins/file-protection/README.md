# file-protection

File protection hooks for Claude Code that guard against accidental overwrites
and encourage modular code.

## Hooks

### PreToolUse: file_hook.py

Unified entry point that runs all file protection checks:

1. **claude_md_check** - Blocks direct writes to CLAUDE.md, suggests AGENTS.md
2. **file_length_check** - Warns when files exceed 10000 lines

## CLAUDE.md Protection

Direct writes to CLAUDE.md are blocked. Instead:

1. Write content to AGENTS.md
2. Create symlink: `ln -s AGENTS.md CLAUDE.md`

This ensures proper version control and agent-agnostic instructions.

## File Length Limits

Uses a "speed bump" pattern:

1. First attempt to write >10000 lines is blocked with a warning
2. A flag file is created
3. Second attempt proceeds (user has acknowledged the warning)
4. Flag is cleared after use

## Configuration

No configuration required. The hooks are automatically loaded by Claude Code
when `CLAUDE_HOOKS_DIR` points to the parent claude-hooks directory.
