#!/usr/bin/env python3
"""WorktreeRemove hook: removes worktrees cleanly."""

import json
import os
import subprocess
import sys


def main():
    data = json.load(sys.stdin)
    worktree_path = data.get('worktree_path', '').strip()

    if not worktree_path or not os.path.isdir(worktree_path):
        # Nothing to remove
        sys.exit(0)

    # Find the main repo via git-common-dir
    result = subprocess.run(
        ['git', 'rev-parse', '--git-common-dir'],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # Worktree path doesn't exist or isn't git — nothing to do
        sys.exit(0)

    # The common dir is the .git directory of the main repo
    common_dir = os.path.realpath(result.stdout.strip())
    main_repo = os.path.dirname(common_dir)

    result = subprocess.run(
        ['git', 'worktree', 'remove', '--force', worktree_path],
        cwd=main_repo,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(json.dumps({'error': result.stderr.strip()}), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
