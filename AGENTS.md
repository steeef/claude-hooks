# claude-hooks

Safety and automation hooks for AI coding agents.

## Project Structure

```text
plugins/
  command-safety/    # Blocks dangerous Bash commands (rm, kubectl delete, etc.)
  git-hooks/         # Enforces git safety (no commits to main, worktree suggestions)
  file-protection/   # Worktree edit guard, CLAUDE.md protection, file length limits
  env-protection/    # Blocks .env file reads, prevents secret exposure
  notifications/     # Desktop notifications on macOS
tests/               # Pytest tests for all plugins
```

## Development

- Python 3.11+, managed with `uv`
- Tests: `uv run pytest -v`
- Linting/formatting: `prek run --files <files>`
- Pre-commit config: `.pre-commit-config.yaml` (ruff, shellcheck, pymarkdown)

## Conventions

- Hooks receive JSON on stdin with `tool_name`, `tool_input`, and `session_id` fields
- Speed bump pattern: deny first, then ask on retry (flag file tracks state)
- Worktree flag uses `session_id` content (not mtime) to tie validity to the calling session
- Tests use fixtures from `tests/conftest.py` (temp git repos, worktrees, cleanup)
- Keep hook scripts small; one concern per sub-module
- Plugin code changes require version bumps in `.claude-plugin/marketplace.json` (CI enforces)
