# claude-hooks

Safety and automation hooks for AI coding agents (Claude Code) — PreToolUse / PostToolUse / Stop hooks that block dangerous commands, enforce git safety, protect files and secrets, and manage worktrees.

## What

- Stack: Python 3.11+, managed with `uv`; pytest for tests; ruff + shellcheck + pymarkdown via pre-commit
- Layout: `plugins/` — one sub-dir per plugin (command-safety, git-hooks, file-protection, env-protection, git-worktree-hooks, notifications); each hook reads JSON on stdin with `tool_name`, `tool_input`, `session_id`
- Layout: `tests/` — pytest tests for all plugins; fixtures in `tests/conftest.py` (temp git repos, worktrees, cleanup)

## How

- Test: `uv run pytest -v`
- Verify: `prek run --files <file1> <file2> ...`

## Index

- README.md — plugin catalog and installation via the Claude Code plugin marketplace

## Lessons

- Speed bump pattern: deny first, then ask on retry (a flag file tracks state).
- Tie worktree flag validity to the calling session via session_id content, not mtime.
- Keep hook scripts small — one concern per sub-module.
- Bump the version in both plugin.json and marketplace.json on any plugin code change (CI enforces).

## Doc Contract

- Re-read this file, plus any Index doc relevant to the area you are touching, before editing code in this repo.
- Do a doc pass after meaningful changes: before finishing work that changed behavior, structure, or commands, update this file or the relevant Index doc — or explicitly decide no doc change is needed.
- Delete stale text immediately; wrong docs are worse than missing docs.
- Prefer file:line pointers over code snippets; snippets rot.
- Hard cap: 200 lines for this file. At the cap, every addition must delete at least as many lines.
- This is the canonical map. Move depth out and index it above: working-context depth for one coherent directory → that area's child AGENTS.md (auto-loaded when working there); cross-cutting depth → a docs/ topic file.
- Children stay shallow and few: one level below root only (never a child below a child), at most a handful, each at a coherent area an agent edits as a unit — not per-folder. When in doubt, keep it in this file.
