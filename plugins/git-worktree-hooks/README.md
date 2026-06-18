# git-worktree-hooks

Bare-container worktree lifecycle hooks. Claude does its file-modifying work in
bare containers under `~/wt`, never in the human's original clones.

## Hooks

### WorktreeCreate: worktree_create.py

On `EnterWorktree`, derives the repo from the most-recent `cd`-intent (recorded
by `cwd_tracker.py` before the harness can snap the cwd back), most-recent first:

- A `cd ~/wt/<repo>` intent names the repo by path — it reuses the existing bare
  container's origin, or (no container yet) infers a clone URL from the origins of
  sibling containers under the base and clones on demand. This is the universal
  entry point: it works with **no human clone present**. When the URL can't be
  inferred (no container, no clear sibling org), it errors asking for the clone
  URL rather than guessing.
- A `cd` into a human clone uses that clone's `origin` remote.

Falls back to the current dir's `origin` when no intent resolves. On a cwd/intent
origin mismatch it prints a non-fatal stale-cwd note to stderr — the worktree
still lands in the intended repo, making a pin-trapped session recoverable with
one `cd`. It then bootstraps a bare container at `~/wt/<repo>/` if absent and
creates (or reuses) a worktree at `~/wt/<repo>/<name>`. Base dir is
`$CLAUDE_WORKTREE_BASE` or `~/wt`.

### WorktreeRemove: worktree_remove.py

Cleans up a bare-container worktree on removal.

### PreToolUse: read_clone_warn.py

Non-blocking warning on `Read`/`Grep`/`Glob` when reading a human clone instead of
a fresh tree. Two cases:

1. A `~/wt` worktree container for the repo **already exists** — a worktree is
   available, but the clone is being read anyway.
2. **No container yet**, but the `~/wt` workflow is in use here (the base holds
   other bare containers) — the first research read of a repo, before any
   worktree. Deduped once per repo per session (cache in `/tmp`) so a multi-file
   exploration warns once, not per read.

The clone may sit on a stale branch or be behind origin, so files look missing or
wrong. The hook **never denies** — it only ever approves, optionally with a
`systemMessage`. Container-path derivation is shared with `worktree_create.py`, so
the "does a worktree exist?" check lines up exactly with where `EnterWorktree`
would have placed it. No org/host/personal path is baked in — the workflow-in-use
gate is inferred from the base.

Silent (no warning) when: the target has no resolvable path, is not in a git repo,
is already under the `~/wt` base, has no `origin` remote, or (case 2) the `~/wt`
workflow is not in use here.

### PreToolUse: enter_worktree_guard.py

Denies `EnterWorktree(path: …)` **only** when the cwd is not inside a git
repository. The `path:` form is handled by the builtin (it does not route through
`WorktreeCreate`) and requires a git-repo cwd, so after `ExitWorktree` — when the
harness resets the cwd to a non-git fallback dir — it fails with an opaque "the
current directory is not in a git repository". This hook turns that dead end into
an actionable redirect: re-enter with `EnterWorktree(name: <branch>)`, which routes
through `worktree_create.py` and reuses the existing worktree from any cwd. A
`path:` switch from inside a git repo, and every `name:` call, are left untouched.
Fail-open: anything else approves.

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
