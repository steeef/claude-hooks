#!/usr/bin/env python3
"""
Worktree Edit Guard Hook

Three-phase speed bump for edits outside a git worktree:
1. First edit  -> deny  (agent sees error + guidance)
2. Second edit -> ask   (user is prompted to approve or switch to worktree)
3. After user approval, subsequent edits are allowed for the session
"""

import contextlib
import json
import os
import subprocess
from pathlib import Path

FLAG_FILENAME = '.claude_worktree_warning.flag'

CONFIG_PATH = Path(os.path.expanduser('~/.config/claude-hooks/config.json'))


def load_config() -> dict:
    """Load config from ~/.config/claude-hooks/config.json."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _is_repo_allowlisted(repo_root: str) -> bool:
    """Check if repo_root is in the worktree_guard_allowlist."""
    config = load_config()
    allowlist = config.get('worktree_guard_allowlist', [])
    resolved_root = os.path.realpath(repo_root)
    for entry in allowlist:
        expanded = os.path.realpath(os.path.expanduser(entry))
        if resolved_root == expanded:
            return True
    return False


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


def _read_flag(flag_path: Path, session_id: str) -> str:
    """Return flag state: 'none', 'warned', or 'approved'."""
    if not flag_path.exists():
        return 'none'
    try:
        content = flag_path.read_text()
    except OSError:
        return 'none'
    if content == f'{session_id}:approved':
        return 'approved'
    if content == session_id:
        return 'warned'
    return 'none'  # different session or corrupt


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

    # Repo is allowlisted — skip worktree guard
    if _is_repo_allowlisted(repo_root):
        return 'allow', None

    flag_path = Path(repo_root) / FLAG_FILENAME

    flag_state = _read_flag(flag_path, session_id)

    # Phase 3: already approved this session → allow
    if flag_state == 'approved':
        return 'allow', None

    # Phase 2: warned once → ask user, optimistically mark approved
    if flag_state == 'warned':
        with contextlib.suppress(OSError):
            flag_path.write_text(f'{session_id}:approved')
        reason = (
            'This edit is outside a git worktree (directly on the main working tree). '
            'Approve to edit in-place, or deny to switch to a worktree first.'
        )
        return 'ask', reason

    # Phase 1: first attempt → deny, set flag
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
