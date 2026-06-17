#!/usr/bin/env python3
"""PreToolUse hook: warn when *researching* a human clone instead of a fresh tree.

The convention is to do file work in bare-container worktrees under ~/wt, never
in the human's original clone. A recurring mistake is *exploring* a repo by
reading the clone's checked-out tree — which may sit on a stale branch or be
behind origin, so files look missing or wrong. This hook fires on Read/Grep/Glob
and emits a NON-BLOCKING warning (it never denies) in two cases:

  1. A ~/wt worktree container for the repo already exists — a fresh worktree is
     available, yet the clone is being read anyway.
  2. No container yet, but the ~/wt workflow is in use here (the base holds other
     bare containers) — the first research read of a repo, before any worktree.
     Deduped once per repo per session so exploration warns once, not per file.

Repo-name / container-path derivation is shared with worktree_create.py (imported,
not copied) so "does a worktree exist?" lines up exactly with where EnterWorktree
would have put it. No org/host/personal path is baked in: the workflow-in-use
gate is inferred from the worktree base ($CLAUDE_WORKTREE_BASE or ~/wt).

Output contract: only ever `{"decision": "approve"}`, optionally with a top-level
`systemMessage` carrying the warning. Fail-open: any error approves silently.
"""

import contextlib
import json
import os
import sys
from pathlib import Path

# Share the exact origin-resolution / container-path logic with the create hook.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worktree_create import (  # noqa: E402
    load_config,
    origin_url,
    repo_name_from_url,
    toplevel,
    worktree_base,
)


def _uses_worktree_workflow(base: Path) -> bool:
    """True when the worktree base holds at least one bare container — i.e. the
    ~/wt workflow is actually in use here. Gates the first-research warning on the
    environment we're running in rather than any hardcoded personal path: with no
    worktree working set, nudging toward EnterWorktree would be irrelevant noise."""
    try:
        return any((d / '.bare').is_dir() for d in base.iterdir())
    except Exception:
        return False


def _warn_cache_path(session_id: str) -> Path:
    return Path('/tmp') / f'.claude_read_warned_{session_id}.json'


def _already_warned(session_id: str | None, repo: str) -> bool:
    """True if `repo` was already first-research-warned this session — and records
    it when not, so a multi-file exploration warns once per repo, not per read. No
    session_id → never suppress (returns False). Fail-open: any error → not warned."""
    if not session_id:
        return False
    cache = _warn_cache_path(session_id)
    try:
        seen = json.loads(cache.read_text())
        if not isinstance(seen, list):
            seen = []
    except Exception:
        seen = []
    if repo in seen:
        return True
    with contextlib.suppress(Exception):
        cache.write_text(json.dumps((seen + [repo])[-500:]))
    return False


def _target_path(tool_name: str, tool_input: dict, cwd: str | None) -> str | None:
    """Resolve the path a Read/Grep/Glob call targets, or None if unresolvable."""
    if tool_name == 'Read':
        path = tool_input.get('file_path')
    elif tool_name in ('Grep', 'Glob'):
        path = tool_input.get('path') or cwd
    else:
        return None
    return path if isinstance(path, str) and path else None


def check_read_clone(tool_name, tool_input, cwd, session_id=None) -> tuple[bool, str | None]:
    """Return (warn, message). warn=True means emit a non-blocking warning.

    Two warning cases, both for a human clone (origin remote, outside the worktree
    base) — never blocks, never raises (caller fails open):
      1. A ~/wt worktree container for the repo already exists → you're reading the
         clone when a fresh worktree is available.
      2. No container yet, but the ~/wt workflow is in use here → the FIRST research
         read of this repo; the clone may be on a stale branch. Deduped once per
         repo per session so multi-file exploration warns once, not per read.
    """
    path = _target_path(tool_name, tool_input or {}, cwd)
    if not path:
        return False, None

    # Config gate: read_clone_warn: false disables the hook. Default = enabled.
    if load_config().get('read_clone_warn') is False:
        return False, None

    target = Path(path)
    target_dir = str(target if target.is_dir() else target.parent)

    repo_root = toplevel(target_dir)
    if not repo_root:
        return False, None

    base = worktree_base().resolve()
    root = Path(repo_root).resolve()
    # Already inside a ~/wt worktree → correct location, say nothing.
    if root == base or root.is_relative_to(base):
        return False, None

    url = origin_url(repo_root)
    if not url:
        return False, None

    repo = repo_name_from_url(url)
    container = worktree_base() / repo
    if container.is_dir():
        return True, (
            f'A ~/wt worktree exists for `{repo}`; you are reading the human clone at '
            f'`{path}`. Explore inside the worktree instead — its files reflect fresh '
            'origin/main; the clone may be on a stale branch.'
        )

    # First research read of a repo with no worktree yet. Only nudge if the ~/wt
    # workflow is actually in use here, and only once per repo per session.
    if not _uses_worktree_workflow(base):
        return False, None
    if _already_warned(session_id, repo):
        return False, None
    return True, (
        f'You are reading the local clone of `{repo}` at `{path}`, which may be on a '
        'stale branch or behind origin. For research, prefer a fresh worktree '
        '(EnterWorktree) or read origin directly (e.g. `gh api '
        f'repos/<org>/{repo}/contents/...`, `gh search code`).'
    )


def main():
    try:
        data = json.load(sys.stdin)
        warn, message = check_read_clone(
            data.get('tool_name'),
            data.get('tool_input', {}),
            data.get('cwd'),
            data.get('session_id'),
        )
    except Exception:
        # Fail-open: never block a read because the warning hook tripped.
        warn, message = False, None

    out = {'decision': 'approve'}
    if warn and message:
        out['systemMessage'] = message
    print(json.dumps(out))
    sys.exit(0)


if __name__ == '__main__':
    main()
