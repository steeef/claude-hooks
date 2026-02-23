#!/usr/bin/env python3
"""
Worktree Edit Guard Hook

Prompts the user (via 'ask') when file edits happen outside a git worktree.
Uses a persistent flag so the prompt only fires once per session.
"""

import subprocess
from pathlib import Path

FLAG_FILE = Path('.claude_worktree_warning.flag')


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
        ('allow', None) — edit is fine (worktree, non-git, or already warned)
        ('ask', reason)  — user must approve editing outside a worktree
    """
    file_path = tool_input.get('file_path', '')
    if not file_path:
        return 'allow', None

    # Already warned this session
    if FLAG_FILE.exists():
        return 'allow', None

    # Not a git repo — worktree concept doesn't apply
    if not _is_inside_git_repo(file_path):
        return 'allow', None

    # Already in a worktree — good practice
    if _is_in_worktree():
        return 'allow', None

    # Editing in main repo without a worktree — prompt the user
    FLAG_FILE.touch()

    reason = (
        'You are editing files in the **main working tree**, not a git worktree.\n\n'
        'Per project conventions, feature work should happen in a worktree '
        '(use `EnterWorktree` to create one).\n\n'
        '**Approve** to continue editing here, or **Deny** to stop and switch '
        'to a worktree first.'
    )

    return 'ask', reason
