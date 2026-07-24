#!/usr/bin/env python3
"""
rm command safety hook - blocks rm but allows git-ignored files.

Checks if target files are git-ignored before allowing deletion.
"""

import os
import re
import shlex
import subprocess
from pathlib import Path


def get_default_handler_path():
    """Path to the bundled default rm-block guidance handler (mv to TRASH/)."""
    return str(Path(__file__).resolve().parent / 'rm_handlers' / 'trash_handler.sh')


def get_rm_handler_path():
    """
    Resolve the rm-block guidance handler.

    Defaults to the bundled trash_handler.sh (mv to TRASH/ + log to
    TRASH-FILES.md, today's behavior). Override with CLAUDE_HOOKS_RM_HANDLER
    to point at your own script/program for a different alternative to `rm`.
    """
    return os.environ.get('CLAUDE_HOOKS_RM_HANDLER') or get_default_handler_path()


def _run_handler_script(handler_path, targets):
    """Run one handler script; return its stdout, or None on any failure."""
    try:
        result = subprocess.run(
            [handler_path, *targets],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def run_rm_handler(targets):
    """
    Run the configured rm-block guidance handler.

    The handler receives the blocked target paths as argv and must print its
    guidance to stdout (exit 0). Its output becomes the "how to fix it" part
    of the hook's reason text, so each handler can describe its own tool's
    usage, recovery, and listing commands however it needs to - nothing
    tool-specific is hardcoded here.

    If a custom CLAUDE_HOOKS_RM_HANDLER is missing, non-executable, errors, or
    times out, falls back to the bundled default handler rather than a
    hardcoded string (so guidance never silently references a tool you're not
    actually using). Only if even the bundled default fails does this return a
    generic, tool-agnostic notice.
    """
    handler_path = get_rm_handler_path()
    guidance = _run_handler_script(handler_path, targets)
    if guidance is not None:
        return guidance

    default_path = get_default_handler_path()
    if handler_path != default_path:
        guidance = _run_handler_script(default_path, targets)
        if guidance is not None:
            return guidance

    return (
        f'rm is blocked, but no guidance is available: the configured handler '
        f'({handler_path}) produced no output. Set CLAUDE_HOOKS_RM_HANDLER to a '
        f'working script, or unset it to use the bundled default.'
    )


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

    # Extract targets from the rm command (used by both branches below,
    # regardless of git-repo status, so the handler always gets them)
    targets = extract_rm_targets(normalized_cmd)

    # Check if we're in a git repo
    if not is_in_git_repo():
        reason_text = (
            'rm command blocked outside of git repository.\n\nInside a git repo, rm is allowed for git-ignored files only.\n\n'
        ) + run_rm_handler(targets)
        return True, reason_text

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

        reason_text = (f'rm blocked for tracked/non-ignored files: {target_list}\n\n') + run_rm_handler(non_ignored_targets)
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
