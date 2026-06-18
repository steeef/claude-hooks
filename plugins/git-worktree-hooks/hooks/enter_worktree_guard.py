#!/usr/bin/env python3
"""PreToolUse(EnterWorktree) hook: deny `path:` re-entry from a non-git cwd.

EnterWorktree has two forms. `name:` routes through this plugin's WorktreeCreate
hook (worktree_create.py), which resolves the repo from cd-intent and reuses an
existing worktree from ANY cwd. `path:` is handled entirely by the builtin, which
requires the current directory to be inside a git repository — so after
ExitWorktree (when the harness resets cwd to a non-git fallback dir) a `path:`
re-entry fails with the opaque "the current directory is not in a git repository".

This hook turns that dead end into an actionable redirect: when `path:` is used
AND the cwd is not in a git repo, deny and tell the model to re-enter with `name:`
instead. Scoped narrowly — a `path:` switch from inside a git repo (the documented
builtin use) is left untouched, as is every `name:` call.

Fully fail-open: any error, or anything that is not a non-git-cwd `path:` call,
approves so the builtin/WorktreeCreate hook handles it as usual.
"""

import json
import subprocess
import sys
from typing import NoReturn


def _approve() -> NoReturn:
    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


def _deny(reason: str) -> NoReturn:
    print(
        json.dumps(
            {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': reason,
                }
            }
        )
    )
    sys.exit(0)


def is_git_repo(cwd: str) -> bool:
    try:
        return (
            subprocess.run(
                ['git', '-C', cwd, 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )
    except Exception:
        return True  # fail-open: can't check → don't block


DENY_REASON = (
    'EnterWorktree(path:) is handled by the builtin, which requires the current '
    'directory to be inside a git repository — and this cwd is not one (it is the '
    'non-git fallback dir the harness resets to after ExitWorktree).\n\n'
    'Re-enter with name: instead — EnterWorktree(name: <branch>). That routes '
    'through the worktree hook, which finds the existing ~/wt/<repo>/<branch> '
    'worktree and returns it from any cwd. If the branch name exists in more than '
    'one repo (ambiguous), cd into the target clone first, then EnterWorktree(name:).'
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _approve()

    if data.get('tool_name') != 'EnterWorktree':
        _approve()

    tool_input = data.get('tool_input') or {}
    path = tool_input.get('path')
    # Only the path: form is at risk; name: routes through WorktreeCreate.
    if not (isinstance(path, str) and path.strip()):
        _approve()

    cwd = data.get('cwd')
    if cwd and not is_git_repo(cwd):
        _deny(DENY_REASON)

    _approve()


if __name__ == '__main__':
    main()
