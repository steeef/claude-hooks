"""Tests for git-worktree-hooks plugin (bare-container model)."""

import json
import os
import subprocess
from types import SimpleNamespace

import pytest

HOOK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'plugins',
    'git-worktree-hooks',
    'hooks',
)


def run_create_hook(input_data, env=None):
    result = subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'worktree_create.py')],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return result


def run_remove_hook(input_data, env=None):
    result = subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'worktree_remove.py')],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return result


def _git(args, cwd):
    subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True)


def _branch_of(worktree_path):
    return subprocess.run(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    """A bare 'remote' + a working clone whose `origin` points at it.

    Yields a namespace with the clone dir (the EnterWorktree cwd), the derived
    repo name, an isolated worktree base, and the env dict to pass the hook so
    bare containers land in tmp (CLAUDE_WORKTREE_BASE) and config defaults
    apply (HOME points at an empty dir).
    """
    src = tmp_path / 'src'
    src.mkdir()
    _git(['init', '-b', 'main'], src)
    _git(['config', 'user.email', 'test@test.com'], src)
    _git(['config', 'user.name', 'Test'], src)
    (src / 'README.md').write_text('# Test Repo\n')
    _git(['add', 'README.md'], src)
    _git(['commit', '-m', 'initial'], src)

    remote = tmp_path / 'myrepo.git'
    _git(['clone', '--bare', str(src), str(remote)], tmp_path)

    clone = tmp_path / 'clone'
    _git(['clone', str(remote), str(clone)], tmp_path)

    home = tmp_path / 'home'
    home.mkdir()
    wt_base = tmp_path / 'wt'
    env = {'CLAUDE_WORKTREE_BASE': str(wt_base), 'HOME': str(home)}

    yield SimpleNamespace(
        clone=clone,
        remote=remote,
        wt_base=wt_base,
        env=env,
        repo_name='myrepo',
    )


class TestBareContainerBootstrap:
    def test_cold_bootstrap_creates_container_and_worktree(self, remote_and_clone):
        rc = remote_and_clone
        result = run_create_hook({'name': 'my-feature', 'cwd': str(rc.clone)}, env=rc.env)
        assert result.returncode == 0, result.stderr

        path = result.stdout.strip()
        container = rc.wt_base / rc.repo_name
        assert path == str(container / 'my-feature')
        # Bare container layout: .bare/ dir + a .git *file* pointing at it.
        assert (container / '.bare').is_dir()
        assert (container / '.git').read_text().strip() == 'gitdir: ./.bare'
        # Worktree is a valid checkout on branch 'my-feature'.
        assert os.path.isdir(path)
        assert _branch_of(path) == 'my-feature'

    def test_prints_only_path_to_stdout(self, remote_and_clone):
        rc = remote_and_clone
        result = run_create_hook({'name': 'clean-out', 'cwd': str(rc.clone)}, env=rc.env)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert os.path.isabs(lines[0])

    def test_idempotent_reentry_returns_same_path(self, remote_and_clone):
        rc = remote_and_clone
        first = run_create_hook({'name': 'dup', 'cwd': str(rc.clone)}, env=rc.env)
        second = run_create_hook({'name': 'dup', 'cwd': str(rc.clone)}, env=rc.env)
        assert first.returncode == 0 and second.returncode == 0
        assert first.stdout.strip() == second.stdout.strip()

    def test_warm_container_reused_for_new_worktree(self, remote_and_clone):
        rc = remote_and_clone
        run_create_hook({'name': 'first', 'cwd': str(rc.clone)}, env=rc.env)
        container = rc.wt_base / rc.repo_name
        # Marker proves the container was not re-cloned on the second call.
        marker = container / '.bare' / 'BOOTSTRAP_MARKER'
        marker.write_text('x')
        result = run_create_hook({'name': 'second', 'cwd': str(rc.clone)}, env=rc.env)
        assert result.returncode == 0, result.stderr
        assert marker.exists()  # same .bare, not a fresh clone
        assert os.path.isdir(container / 'second')

    def test_tracks_existing_remote_branch(self, remote_and_clone):
        rc = remote_and_clone
        _git(['checkout', '-b', 'feature/x'], rc.clone)
        _git(['push', '-u', 'origin', 'feature/x'], rc.clone)
        result = run_create_hook({'name': 'feature/x', 'cwd': str(rc.clone)}, env=rc.env)
        assert result.returncode == 0, result.stderr
        path = result.stdout.strip()
        assert _branch_of(path) == 'feature/x'

    def test_copies_env_files_into_worktree(self, remote_and_clone):
        rc = remote_and_clone
        (rc.clone / '.env').write_text('SECRET=1\n')
        (rc.clone / '.env.local').write_text('LOCAL=2\n')
        result = run_create_hook({'name': 'with-env', 'cwd': str(rc.clone)}, env=rc.env)
        assert result.returncode == 0, result.stderr
        assert (rc.wt_base / rc.repo_name / 'with-env' / '.env').read_text() == 'SECRET=1\n'
        assert (rc.wt_base / rc.repo_name / 'with-env' / '.env.local').read_text() == 'LOCAL=2\n'

    def test_errors_without_origin_remote(self, temp_git_repo):
        # temp_git_repo has no 'origin' remote → cannot derive the repo.
        result = run_create_hook({'name': 'x', 'cwd': str(temp_git_repo)})
        assert result.returncode == 1
        assert 'origin' in result.stderr

    def test_fails_on_missing_name(self, remote_and_clone):
        result = run_create_hook({'cwd': str(remote_and_clone.clone)}, env=remote_and_clone.env)
        assert result.returncode == 1

    def test_fails_on_empty_name(self, remote_and_clone):
        result = run_create_hook({'name': '', 'cwd': str(remote_and_clone.clone)}, env=remote_and_clone.env)
        assert result.returncode == 1


class TestWorktreeRemove:
    def test_remove_cleans_up_bare_container_worktree(self, remote_and_clone):
        rc = remote_and_clone
        create = run_create_hook({'name': 'to-remove', 'cwd': str(rc.clone)}, env=rc.env)
        assert create.returncode == 0, create.stderr
        path = create.stdout.strip()
        assert os.path.isdir(path)

        remove = run_remove_hook({'worktree_path': path}, env=rc.env)
        assert remove.returncode == 0, remove.stderr
        assert not os.path.isdir(path)

    def test_remove_handles_missing_path(self):
        assert run_remove_hook({'worktree_path': '/nonexistent/path'}).returncode == 0

    def test_remove_handles_empty_path(self):
        assert run_remove_hook({'worktree_path': ''}).returncode == 0
