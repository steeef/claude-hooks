"""Tests for git-worktree-hooks plugin (bare-container model)."""

import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

HOOK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'plugins',
    'git-worktree-hooks',
    'hooks',
)

# Single source of truth for the intent file path — same helper the hooks use.
sys.path.insert(0, HOOK_DIR)
from cwd_tracker import intent_path  # noqa: E402


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


def run_tracker_hook(input_data, env=None):
    return subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'cwd_tracker.py')],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _make_clone(tmp_path, label):
    """A bare 'remote' + a working clone whose origin points at it, under a
    `label`-named subtree so distinct clones have distinct origin URLs."""
    root = tmp_path / label
    root.mkdir()
    src = root / 'src'
    src.mkdir()
    _git(['init', '-b', 'main'], src)
    _git(['config', 'user.email', 'test@test.com'], src)
    _git(['config', 'user.name', 'Test'], src)
    (src / 'README.md').write_text('# Test Repo\n')
    _git(['add', 'README.md'], src)
    _git(['commit', '-m', 'initial'], src)
    remote = root / f'{label}.git'
    _git(['clone', '--bare', str(src), str(remote)], root)
    clone = root / 'clone'
    _git(['clone', str(remote), str(clone)], root)
    return clone


@pytest.fixture
def session():
    """A unique session_id plus auto-cleanup of its /tmp intent file (which
    lives outside tmp_path and would otherwise leak between tests)."""
    sid = f'pytest-{uuid.uuid4().hex}'
    intent = intent_path(sid)

    def seed(entries):
        intent.write_text(json.dumps(entries))

    ns = SimpleNamespace(id=sid, intent=intent, seed=seed)
    try:
        yield ns
    finally:
        intent.unlink(missing_ok=True)


@pytest.fixture
def two_clones(tmp_path):
    """Two human clones with distinct origin URLs + an isolated worktree base.

    `repo_a`/`repo_b` are clone dirs (EnterWorktree cwds); `name_a`/`name_b` are
    the repo names the guard message will print.
    """
    clone_a = _make_clone(tmp_path, 'alpha')
    clone_b = _make_clone(tmp_path, 'beta')
    home = tmp_path / 'home'
    home.mkdir()
    wt_base = tmp_path / 'wt'
    env = {'CLAUDE_WORKTREE_BASE': str(wt_base), 'HOME': str(home)}
    return SimpleNamespace(
        repo_a=clone_a,
        repo_b=clone_b,
        name_a='alpha',
        name_b='beta',
        wt_base=wt_base,
        env=env,
    )


class TestCwdTracker:
    def test_parses_cd_and_git_c_from_compound_command(self, session):
        cmd = 'cd /repo/one && git -C /repo/two status && echo done'
        result = run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': '/start/here',
                'tool_input': {'command': cmd},
            }
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
        entries = json.loads(session.intent.read_text())
        # cwd is context; cd is a move (intent=True); git -C is a peek (False).
        assert entries[0] == {'path': '/start/here', 'intent': False}
        assert {'path': '/repo/one', 'intent': True} in entries
        assert {'path': '/repo/two', 'intent': False} in entries
        # cd before git -C in command order.
        idx_one = entries.index({'path': '/repo/one', 'intent': True})
        idx_two = entries.index({'path': '/repo/two', 'intent': False})
        assert idx_one < idx_two

    def test_appends_across_calls(self, session):
        run_tracker_hook({'tool_name': 'Bash', 'session_id': session.id, 'cwd': '/a', 'tool_input': {'command': 'cd /a'}})
        run_tracker_hook({'tool_name': 'Bash', 'session_id': session.id, 'cwd': '/a', 'tool_input': {'command': 'cd /b'}})
        entries = json.loads(session.intent.read_text())
        intent_paths = [e['path'] for e in entries if e['intent']]
        assert intent_paths == ['/a', '/b']

    def test_non_bash_tool_writes_nothing(self, session):
        result = run_tracker_hook({'tool_name': 'Read', 'session_id': session.id, 'tool_input': {'file_path': '/x'}})
        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
        assert not session.intent.exists()

    def test_missing_session_id_writes_nothing(self):
        result = run_tracker_hook({'tool_name': 'Bash', 'cwd': '/a', 'tool_input': {'command': 'cd /b'}})
        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}

    def test_malformed_input_fails_open(self):
        result = subprocess.run(
            ['python3', os.path.join(HOOK_DIR, 'cwd_tracker.py')],
            input='not json{',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}


class TestMultiRepoGuard:
    def test_single_repo_session_creates(self, two_clones, session):
        tc = two_clones
        session.seed([{'path': str(tc.repo_a), 'intent': True}])
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr

    def test_two_repos_recent_intent_matches_cwd_creates(self, two_clones, session):
        tc = two_clones
        # Touched both, but the most-recent cd-intent lands in the cwd's repo.
        session.seed(
            [
                {'path': str(tc.repo_b), 'intent': True},
                {'path': str(tc.repo_a), 'intent': True},
            ]
        )
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr

    def test_two_repos_recent_intent_mismatch_refuses(self, two_clones, session):
        tc = two_clones
        # Most-recent cd-intent is repo_b, but EnterWorktree cwd is repo_a.
        session.seed(
            [
                {'path': str(tc.repo_a), 'intent': True},
                {'path': str(tc.repo_b), 'intent': True},
            ]
        )
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 1
        assert tc.name_a in result.stderr  # target repo named
        assert tc.name_b in result.stderr  # other repo named
        # Worktree must NOT have been created.
        assert not (tc.wt_base / tc.name_a / 'feat').exists()

    def test_missing_intent_file_falls_through_to_create(self, two_clones, session):
        tc = two_clones
        # session.intent never seeded → unreadable state → fail-open create.
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr

    def test_missing_session_id_falls_through_to_create(self, two_clones):
        tc = two_clones
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a)}, env=tc.env)
        assert result.returncode == 0, result.stderr

    def test_git_c_peek_into_other_repo_does_not_refuse(self, two_clones, session):
        tc = two_clones
        # Real workflow: cd into the intended clone (repo_a), then a read-only
        # `git -C repo_b` peek. The peek touches repo_b but is NOT a move, so the
        # most-recent intent is still repo_a → EnterWorktree must succeed.
        run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': str(tc.repo_a),
                'tool_input': {'command': f'cd {tc.repo_a} && git -C {tc.repo_b} status'},
            }
        )
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr

    def test_tracker_to_guard_round_trip_refuses(self, two_clones, session):
        tc = two_clones
        # Exercise the REAL writer→reader contract (not a hand-seeded file): the
        # tracker records cd into repo_a then cd into repo_b; EnterWorktree fires
        # from repo_a (stale cwd) → most-recent intent (repo_b) ≠ target → refuse.
        run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': str(tc.repo_a),
                'tool_input': {'command': f'cd {tc.repo_a}'},
            }
        )
        run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': str(tc.repo_a),
                'tool_input': {'command': f'cd {tc.repo_b}'},
            }
        )
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 1
        assert tc.name_a in result.stderr and tc.name_b in result.stderr

    def test_idempotent_reentry_never_refused(self, two_clones, session):
        tc = two_clones
        # First create succeeds in repo_a.
        first = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert first.returncode == 0, first.stderr
        # Now poison intent so a NEW creation would be refused, then re-enter the
        # existing worktree: the early-return must win, never refused.
        session.seed(
            [
                {'path': str(tc.repo_a), 'intent': True},
                {'path': str(tc.repo_b), 'intent': True},
            ]
        )
        second = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip() == first.stdout.strip()


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
