#!/usr/bin/env python3
"""
Worktree Edit Guard Hook

Two-phase speed bump for edits outside a git worktree:
1. First edit  → deny  (agent sees error + guidance)
2. Second edit → ask   (user is prompted to approve or switch to worktree)
3. Cycle resets after the ask step
"""

import contextlib
import subprocess
import time
from pathlib import Path

FLAG_FILE = Path('.claude_worktree_warning.flag')
FLAG_TTL_SECONDS = 300  # 5 minutes


def _flag_is_valid() -> bool:
    """Return True if the flag file exists and its mtime is within TTL."""
    if not FLAG_FILE.exists():
        return False
    try:
        age = time.time() - FLAG_FILE.stat().st_mtime
        if age <= FLAG_TTL_SECONDS:
            return True
    except OSError:
        pass
    # Stale or unreadable — remove and treat as absent
    with contextlib.suppress(OSError):
        FLAG_FILE.unlink()
    return False


def _is_inside_git_repo(file_path: str) -> bool:
    """Check if file_path is inside a git repository."""
    try:
        target_dir = str(Path(file_path).parent)
        result = subprocess.run(
            ['git', '-C', target_dir, 'rev-parse', '--is-inside-work-tree'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == 'true'
    except Exception:
        return False


def _is_in_worktree() -> bool:
    """Check if we're currently in a worktree (not the main repo)."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-common-dir'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_common = result.stdout.strip() if result.returncode == 0 else None

        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_dir = result.stdout.strip() if result.returncode == 0 else None

        # If git-dir contains "worktrees", we're in a worktree
        if git_dir and 'worktrees' in git_dir:
            return True

        # Alternative check: if common-dir != git-dir, we're in a worktree
        if git_common and git_dir and git_common != git_dir:
            return True

    except Exception:
        pass

    return False


def check_worktree_edit(tool_name: str, tool_input: dict) -> tuple[str, str | None]:
    """
    Check if a file edit is happening outside a git worktree.

    Returns:
        ('allow', None)  — edit is fine (worktree or non-git)
        ('deny', reason)  — first attempt; agent should decide based on scope
        ('ask', reason)   — second attempt; user is prompted to approve
    """
    file_path = tool_input.get('file_path', '')
    if not file_path:
        return 'allow', None

    # Not a git repo — worktree concept doesn't apply
    if not _is_inside_git_repo(file_path):
        return 'allow', None

    # Already in a worktree — good practice
    if _is_in_worktree():
        return 'allow', None

    # Phase 2: flag exists and is fresh → ask the user, then reset
    if _flag_is_valid():
        FLAG_FILE.unlink(missing_ok=True)
        reason = (
            'This edit is outside a git worktree (directly on the main working tree). '
            'Approve to edit in-place, or deny to switch to a worktree first.'
        )
        return 'ask', reason

    # Phase 1: no flag or stale → deny and set flag
    FLAG_FILE.touch()
    reason = (
        'WORKTREE GUARD: This edit targets the main working tree, not a worktree.\n'
        '\n'
        '• If you are implementing a plan, feature, or multi-file change:\n'
        '  Use EnterWorktree to create a worktree. Do NOT retry this edit.\n'
        '\n'
        '• If this is a trivial/single-file fix (typo, config tweak, docs):\n'
        '  Retry the edit — the user will be prompted to approve.\n'
        '\n'
        'Project convention: significant work belongs in worktrees.'
    )
    return 'deny', reason
