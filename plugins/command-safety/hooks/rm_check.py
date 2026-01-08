#!/usr/bin/env python3
"""
rm command safety hook - blocks rm but allows git-ignored files.

Checks if target files are git-ignored before allowing deletion.
"""

import os
import re
import shlex
import subprocess


def is_in_git_repo():
    """Check if current directory is in a git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_git_ignored(path):
    """
    Check if path is ignored by git (gitignore, exclude, global).

    For directories, check the directory path only (not recursive contents).
    """
    try:
        # Normalize path
        abs_path = os.path.abspath(path)
        cwd = os.path.dirname(abs_path) or '.'

        result = subprocess.run(
            ['git', 'check-ignore', '-q', path],
            capture_output=True,
            cwd=cwd,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False  # If git check fails, assume not ignored (safer)


def extract_rm_targets(command):
    """
    Extract target paths from rm command.

    Handles flags like -r, -f, -rf, etc.
    Returns list of target paths.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return []

    targets = []
    skip_next = False

    for i, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue

        # Skip the rm command itself
        if i == 0 and (part == 'rm' or part.endswith('/rm')):
            continue

        # Skip flags
        if part.startswith('-'):
            # Handle flags that take arguments (rare for rm)
            continue

        # This is a target path
        targets.append(part)

    return targets


def check_rm_command(command):
    """
    Check if a command contains rm that should be blocked.

    Returns tuple: (should_block: bool, reason: str or None)

    Allows rm if:
    - Inside a git repo AND all targets are git-ignored

    Blocks rm if:
    - Outside a git repo
    - Any target is tracked or not ignored
    """
    # Normalize the command
    normalized_cmd = ' '.join(command.strip().split())

    # Check if it's an rm command
    # This catches: rm, /bin/rm, /usr/bin/rm, etc.
    if not (normalized_cmd.startswith('rm ') or normalized_cmd == 'rm' or re.search(r'(^|[;&|]\s*)(/\S*/)?rm\b', normalized_cmd)):
        return False, None

    # Check if we're in a git repo
    if not is_in_git_repo():
        reason_text = (
            'rm command blocked outside of git repository.\n\n'
            'Inside a git repo, rm is allowed for git-ignored files only.\n'
            'Outside git repos, use mv to move files to TRASH/ instead.'
        )
        return True, reason_text

    # Extract targets from the rm command
    targets = extract_rm_targets(normalized_cmd)

    if not targets:
        # No targets found, let rm handle the error
        return False, None

    # Check each target
    non_ignored_targets = []
    for target in targets:
        # Strip trailing slashes for consistency
        target_clean = target.rstrip('/')

        if not is_git_ignored(target_clean):
            non_ignored_targets.append(target)

    if non_ignored_targets:
        # Some targets are not git-ignored - block
        target_list = ', '.join(non_ignored_targets[:5])
        if len(non_ignored_targets) > 5:
            target_list += f' (+{len(non_ignored_targets) - 5} more)'

        reason_text = (
            f'rm blocked for tracked/non-ignored files: {target_list}\n\n'
            "Instead of using 'rm':\n"
            '- MOVE files using `mv` to the TRASH directory in the CURRENT folder '
            '(create it if needed)\n'
            "- Add an entry in 'TRASH-FILES.md' in the current directory:\n\n"
            '```\n'
            'test_script.py - moved to TRASH/ - temporary test script\n'
            '```\n\n'
            'Note: rm is allowed for git-ignored files (e.g., .DS_Store, node_modules/).'
        )
        return True, reason_text

    # All targets are git-ignored - allow
    return False, None


# If run as a standalone script
if __name__ == '__main__':
    import json
    import sys

    data = json.load(sys.stdin)

    # Check if this is a Bash tool call
    tool_name = data.get('tool_name')
    if tool_name != 'Bash':
        print(json.dumps({'decision': 'approve'}))
        sys.exit(0)

    # Get the command being executed
    command = data.get('tool_input', {}).get('command', '')

    should_block, reason = check_rm_command(command)

    if should_block:
        print(json.dumps({'decision': 'block', 'reason': reason}, ensure_ascii=False))
    else:
        print(json.dumps({'decision': 'approve'}))

    sys.exit(0)
