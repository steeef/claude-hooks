#!/usr/bin/env python3
"""WorktreeCreate hook: creates worktrees with clean branch names (no worktree- prefix)."""

import json
import os
import subprocess
import sys


def get_repo_root(cwd):
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_default_base(cwd):
    result = subprocess.run(
        ['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # Fallback: check if origin/main exists
    result = subprocess.run(
        ['git', 'rev-parse', '--verify', 'origin/main'],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return 'origin/main'
    return None


def branch_exists(cwd, branch_name):
    result = subprocess.run(
        ['git', 'rev-parse', '--verify', branch_name],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main():
    data = json.load(sys.stdin)
    name = data.get('name', '').strip()

    if not name:
        print(json.dumps({'error': 'missing required field: name'}), file=sys.stderr)
        sys.exit(1)

    cwd = data.get('cwd', '.')
    repo_root = get_repo_root(cwd)
    if not repo_root:
        print(json.dumps({'error': 'not inside a git repository'}), file=sys.stderr)
        sys.exit(1)

    worktree_dir = f'{repo_root}/.claude/worktrees/{name}'
    branch_name = name

    # If worktree directory already exists and is valid, return it (idempotent re-entry)
    if os.path.isdir(worktree_dir):
        verify = subprocess.run(
            ['git', '-C', worktree_dir, 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True,
        )
        if verify.returncode == 0:
            print(worktree_dir)
            sys.exit(0)

    if branch_exists(repo_root, branch_name):
        # Reuse existing branch
        result = subprocess.run(
            ['git', 'worktree', 'add', worktree_dir, branch_name],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    else:
        # Create new branch from default base
        base = get_default_base(repo_root)
        cmd = ['git', 'worktree', 'add', '-b', branch_name, worktree_dir]
        if base:
            cmd.append(base)
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        print(json.dumps({'error': result.stderr.strip()}), file=sys.stderr)
        sys.exit(1)

    # Print only the worktree path to stdout (required by Claude Code)
    print(worktree_dir)


if __name__ == '__main__':
    main()
