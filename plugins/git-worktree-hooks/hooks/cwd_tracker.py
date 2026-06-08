#!/usr/bin/env python3
"""PreToolUse(Bash) hook: record per-session directory intent.

Multi-repo tickets are the failure mode this addresses: a session `cd`s between
two human clones, then calls EnterWorktree while the harness has pinned the cwd
to the wrong one, and a worktree is created in the wrong repo. This hook captures
the *intent* — every `cd <path>` and `git -C <path>` target, plus the call's own
cwd — into an ordered per-session list. `worktree_create.py` reads that list and
*derives its target repo* from the most-recent cd-intent, falling back to cwd
only when none resolves to a clone (and warning when the two disagree).

Entries are tagged `intent` (an explicit `cd` target — the leading signal of
where the agent means to be) vs context (the call's own `cwd` and `git -C` peeks
— `cwd` is a lagging signal the harness residual-cwd-pin can hold stale; a
`git -C <other>` peek is a read, not a move). The distinction is load-bearing:
EnterWorktree picks the most-recent `intent=True` entry as its target, so a peek
into another repo must NOT count as intent or it would mis-target. Because this
hook parses the command string in PreToolUse — before execution — the recorded
intent survives the harness snap-back that traps the cwd.

Design constraints:
  - Pure string parsing. NO git subprocess per Bash call (repo resolution is
    deferred to the WorktreeCreate hook, which runs far less often).
  - Always allow. This hook never blocks or slows Bash.
  - Fully fail-open: any error → approve. State is best-effort.

State file: /tmp/.claude_worktree_intent_{session_id}.json — a JSON list of
{"path": str, "intent": bool} entries in chronological order. Keyed by
session_id so concurrent multi-repo sessions never cross-contaminate.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import NoReturn

# Bound the list so a long session can't grow the file without limit.
MAX_PATHS = 200


def _approve() -> NoReturn:
    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


def intent_path(session_id: str) -> Path:
    return Path('/tmp') / f'.claude_worktree_intent_{session_id}.json'


def extract_subcommands(command: str) -> list[str]:
    """Split a compound bash command on &&, ||, and ; (vendored, see
    git_branch_workflow.py — plugins do not import across each other)."""
    if not command:
        return []
    return [c.strip() for c in re.split(r'\s*(?:&&|\|\||;)\s*', command) if c.strip()]


def extract_cd_target(subcmd: str) -> str | None:
    """Expanded target dir of a `cd <path>` subcommand, else None."""
    try:
        parts = shlex.split(subcmd)
    except Exception:
        return None
    if len(parts) >= 2 and parts[0] == 'cd':
        return os.path.expanduser(parts[1])
    return None


def extract_git_c_target(subcmd: str) -> str | None:
    """Expanded path of a `git -C <path>` / `git -C<path>` subcommand, else None."""
    try:
        parts = shlex.split(subcmd)
    except Exception:
        return None
    if len(parts) < 2 or parts[0] != 'git':
        return None
    i = 1
    while i < len(parts):
        if parts[i] == '-C' and i + 1 < len(parts):
            return os.path.expanduser(parts[i + 1])
        if parts[i].startswith('-C') and len(parts[i]) > 2:
            return os.path.expanduser(parts[i][2:])
        i += 1
    return None


def _resolve(target: str, base: str | None) -> str:
    """Absolutize a parsed path target. Relative targets resolve against `base`
    (the running cwd) so the guard — which resolves these paths in a SEPARATE
    process — does not misread `cd ../other-repo` against the wrong directory.
    A relative target with no known base is stored as-is (best effort)."""
    if os.path.isabs(target):
        return os.path.normpath(target)
    if base:
        return os.path.normpath(os.path.join(base, target))
    return target


def collect_entries(command: str, cwd: str | None) -> list[dict]:
    """Ordered entries for one Bash call, in command order.

    `intent=True` is reserved for an explicit `cd` — the strong "I am moving
    here" signal the guard uses as most-recent intent. The call's `cwd` and any
    `git -C <path>` are `intent=False`: they count toward repos-touched but must
    NOT set most-recent intent. `git -C <other> log` is a read-only peek, not a
    move; treating it as intent would spuriously refuse a correct EnterWorktree
    that follows a peek into another repo.

    Paths are absolutized as parsed: a `cd` updates the running cwd for later
    subcommands, so chained `cd a && cd ../b` and bare `cd ../other` resolve to
    the right repo rather than a relative string the guard can't re-resolve."""
    entries: list[dict] = []
    running = cwd
    if cwd:
        entries.append({'path': cwd, 'intent': False})
    for subcmd in extract_subcommands(command):
        cd_target = extract_cd_target(subcmd)
        if cd_target:
            resolved = _resolve(cd_target, running)
            entries.append({'path': resolved, 'intent': True})
            running = resolved  # cd moves cwd for subsequent subcommands
            continue
        git_c_target = extract_git_c_target(subcmd)
        if git_c_target:
            entries.append({'path': _resolve(git_c_target, running), 'intent': False})
    return entries


def append_entries(session_id: str, entries: list[dict]) -> None:
    """Append entries to the session intent file, capped at MAX_PATHS."""
    path = intent_path(session_id)
    existing: list[dict] = []
    try:
        loaded = json.loads(path.read_text())
        if isinstance(loaded, list):
            existing = [e for e in loaded if isinstance(e, dict) and 'path' in e]
    except Exception:
        existing = []  # missing/corrupt file → start fresh
    combined = (existing + entries)[-MAX_PATHS:]
    path.write_text(json.dumps(combined))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _approve()

    if data.get('tool_name') != 'Bash':
        _approve()

    session_id = data.get('session_id')
    if not session_id:
        _approve()

    try:
        command = data.get('tool_input', {}).get('command', '') or ''
        entries = collect_entries(command, data.get('cwd'))
        if entries:
            append_entries(session_id, entries)
    except Exception:
        pass  # Fail-open: tracking is best-effort, never block Bash.

    _approve()


if __name__ == '__main__':
    main()
