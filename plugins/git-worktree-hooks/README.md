# git-worktree-hooks

Bare-container worktree lifecycle hooks. Claude does its file-modifying work in
bare containers under `~/wt`, never in the human's original clones.

## Hooks

### WorktreeCreate: worktree_create.py

On `EnterWorktree`, derives the repo from the current dir's `origin` remote,
bootstraps a bare container at `~/wt/<repo>/` if absent, and creates (or reuses)
a worktree at `~/wt/<repo>/<name>`. Base dir is `$CLAUDE_WORKTREE_BASE` or `~/wt`.

### WorktreeRemove: worktree_remove.py

Cleans up a bare-container worktree on removal.

### PreToolUse: read_clone_warn.py

Non-blocking warning on `Read`/`Grep`/`Glob`. Fires when the target path lives in
a human clone for which a `~/wt` worktree container **already exists** — i.e. a
worktree is available, but the clone is being read anyway. The clone may sit on a
stale branch, so files look missing or wrong; the worktree reflects fresh
`origin/main`. The hook **never denies** — it only ever approves, optionally with
a `systemMessage`. Container-path derivation is shared with `worktree_create.py`,
so the "does a worktree exist?" check lines up exactly with where `EnterWorktree`
would have placed it.

Silent (no warning) when: the target has no resolvable path, is not in a git repo,
is already under the `~/wt` base, has no `origin` remote, or no container exists.

## Configuration

`~/.config/claude-hooks/config.json`:

```json
{
  "read_clone_warn": false
}
```

- `read_clone_warn` — set to `false` to disable the read-clone warning. Defaults
  to enabled when the key is absent.
- `CLAUDE_WORKTREE_BASE` (env) — overrides the `~/wt` base dir for containers;
  the warning hook uses the same base when checking for an existing worktree.
