"""Tests for git-worktree-hooks plugin."""

import json
import os
import subprocess

HOOK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'plugins',
    'git-worktree-hooks',
    'hooks',
)


def run_create_hook(input_data):
    result = subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'worktree_create.py')],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
    )
    return result


def run_remove_hook(input_data):
    result = subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'worktree_remove.py')],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
    )
    return result


class TestWorktreeCreate:
    def test_create_uses_name_as_branch(self, temp_git_repo):
        result = run_create_hook({'name': 'my-feature', 'cwd': str(temp_git_repo)})
        assert result.returncode == 0

        worktree_path = result.stdout.strip()
        assert worktree_path.endswith('.claude/worktrees/my-feature')

        # Verify the branch name is exactly 'my-feature', not 'worktree-my-feature'
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        assert branch.stdout.strip() == 'my-feature'

    def test_create_prints_only_path_to_stdout(self, temp_git_repo):
        result = run_create_hook({'name': 'clean-output', 'cwd': str(temp_git_repo)})
        assert result.returncode == 0

        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert os.path.isabs(lines[0])

    def test_create_reuses_existing_branch(self, temp_git_repo):
        # Create a branch first
        subprocess.run(
            ['git', 'branch', 'existing-branch'],
            cwd=temp_git_repo,
            capture_output=True,
        )

        result = run_create_hook({'name': 'existing-branch', 'cwd': str(temp_git_repo)})
        assert result.returncode == 0

        worktree_path = result.stdout.strip()
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        assert branch.stdout.strip() == 'existing-branch'

    def test_create_fails_on_missing_name(self, temp_git_repo):
        result = run_create_hook({'cwd': str(temp_git_repo)})
        assert result.returncode == 1

    def test_create_fails_on_empty_name(self, temp_git_repo):
        result = run_create_hook({'name': '', 'cwd': str(temp_git_repo)})
        assert result.returncode == 1


class TestWorktreeRemove:
    def test_remove_cleans_up_worktree(self, temp_git_repo):
        # Create a worktree first
        create_result = run_create_hook({'name': 'to-remove', 'cwd': str(temp_git_repo)})
        assert create_result.returncode == 0
        worktree_path = create_result.stdout.strip()
        assert os.path.isdir(worktree_path)

        # Remove it
        remove_result = run_remove_hook({'worktree_path': worktree_path})
        assert remove_result.returncode == 0
        assert not os.path.isdir(worktree_path)

    def test_remove_handles_missing_path(self):
        result = run_remove_hook({'worktree_path': '/nonexistent/path'})
        assert result.returncode == 0

    def test_remove_handles_empty_path(self):
        result = run_remove_hook({'worktree_path': ''})
        assert result.returncode == 0
