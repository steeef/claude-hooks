#!/usr/bin/env python3
"""
Worktree Edit Guard Hook

Two-phase speed bump for edits outside a git worktree:
1. First edit  -> deny  (agent sees error + guidance)
2. Second edit -> ask   (user is prompted to approve or switch to worktree)
3. Cycle resets after the ask step
"""

import contextlib
import subprocess
from pathlib import Path

FLAG_FILENAME = '.claude_worktree_warning.flag'


def _get_repo_root(target_dir: str) -> str | None:
    """Return the git repo root for target_dir, or None if not in a repo."""
    try:
        result = subprocess.run(
            ['git', '-C', target_dir, 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _flag_is_valid(flag_path: Path, session_id: str) -> bool:
    """Return True if the flag file exists and contains the given session_id."""
    if not flag_path.exists():
        return False
    try:
        return flag_path.read_text() == session_id
    except OSError:
        return False


def _is_in_worktree(target_dir: str) -> bool:
    """Check if target_dir is inside a worktree (not the main repo)."""
    try:
        result = subprocess.run(
            ['git', '-C', target_dir, 'rev-parse', '--git-common-dir', '--git-dir'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return False

        git_common = lines[0].strip()
        git_dir = lines[1].strip()

        # If git-dir contains "worktrees", we're in a worktree
        if 'worktrees' in git_dir:
            return True

        # Resolve relative paths before comparing (subdirectories return
        # relative git-common-dir but absolute git-dir, causing false positives)
        resolved_common = str(Path(target_dir, git_common).resolve())
        resolved_dir = str(Path(target_dir, git_dir).resolve())
        if resolved_common != resolved_dir:
            return True

    except Exception:
        pass

    return False


def check_worktree_edit(tool_name: str, tool_input: dict, session_id: str | None = None) -> tuple[str, str | None]:
    """
    Check if a file edit is happening outside a git worktree.

    Returns:
        ('allow', None)  -- edit is fine (worktree, non-git, or no session_id)
        ('deny', reason)  -- first attempt; agent should decide based on scope
        ('ask', reason)   -- second attempt; user is prompted to approve
    """
    if not session_id:
        return 'allow', None

    file_path = tool_input.get('file_path', '')
    if not file_path:
        return 'allow', None

    target_dir = str(Path(file_path).parent)

    # Not a git repo -- worktree concept doesn't apply
    repo_root = _get_repo_root(target_dir)
    if repo_root is None:
        return 'allow', None

    # Already in a worktree -- good practice
    if _is_in_worktree(target_dir):
        return 'allow', None

    flag_path = Path(repo_root) / FLAG_FILENAME

    # Phase 2: flag exists and belongs to this session -> ask the user, then reset
    if _flag_is_valid(flag_path, session_id):
        flag_path.unlink(missing_ok=True)
        reason = (
            'This edit is outside a git worktree (directly on the main working tree). '
            'Approve to edit in-place, or deny to switch to a worktree first.'
        )
        return 'ask', reason

    # Phase 1: no flag or different session -> deny and set flag
    with contextlib.suppress(OSError):
        flag_path.write_text(session_id)
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
