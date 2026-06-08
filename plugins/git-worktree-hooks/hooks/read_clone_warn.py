#!/usr/bin/env python3
"""PreToolUse hook: warn when reading a human clone that already has a worktree.

The convention is to do file work in bare-container worktrees under ~/wt, never
in the human's original clone. A recurring mistake is *exploring* a repo by
reading the clone's checked-out tree — which may sit on a stale branch, so files
look missing or wrong. This hook fires on Read/Grep/Glob and emits a NON-BLOCKING
warning (it never denies) when the target lives in a clone for which a ~/wt
worktree container already exists. That is the high-signal case: a worktree is
available, yet the clone is being read anyway.

Repo-name / container-path derivation is shared with worktree_create.py (imported,
not copied) so "does a worktree exist?" lines up exactly with where EnterWorktree
would have put it.

Output contract: only ever `{"decision": "approve"}`, optionally with a top-level
`systemMessage` carrying the warning. Fail-open: any error approves silently.
"""

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


def _target_path(tool_name: str, tool_input: dict, cwd: str | None) -> str | None:
    """Resolve the path a Read/Grep/Glob call targets, or None if unresolvable."""
    if tool_name == 'Read':
        path = tool_input.get('file_path')
    elif tool_name in ('Grep', 'Glob'):
        path = tool_input.get('path') or cwd
    else:
        return None
    return path if isinstance(path, str) and path else None


def check_read_clone(tool_name, tool_input, cwd) -> tuple[bool, str | None]:
    """Return (warn, message). warn=True means emit a non-blocking warning.

    Approves silently (False, None) unless the target sits in a human clone whose
    ~/wt worktree container already exists. Never raises — the caller fails open.
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
    if not container.is_dir():
        return False, None

    message = (
        f'A ~/wt worktree exists for `{repo}`; you are reading the human clone at '
        f'`{path}`. Explore inside the worktree instead — its files reflect fresh '
        'origin/main; the clone may be on a stale branch.'
    )
    return True, message


def main():
    try:
        data = json.load(sys.stdin)
        warn, message = check_read_clone(
            data.get('tool_name'),
            data.get('tool_input', {}),
            data.get('cwd'),
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
