"""Tests for git-worktree-hooks plugin (bare-container model)."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
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
from worktree_create import (  # noqa: E402
    infer_clone_url,
    origin_url,
    resolve_target,
    wt_repo_segment,
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


def run_read_clone_hook(input_data, env=None, raw=None):
    """Run the read_clone_warn hook. Pass `raw` to send non-JSON stdin."""
    result = subprocess.run(
        ['python3', os.path.join(HOOK_DIR, 'read_clone_warn.py')],
        input=raw if raw is not None else json.dumps(input_data),
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
        # read_clone_warn's once-per-repo-per-session cache also lives in /tmp.
        Path(f'/tmp/.claude_read_warned_{sid}.json').unlink(missing_ok=True)


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

    def test_resolves_relative_targets_against_running_cwd(self, session):
        # Relative cd/git -C must be absolutized in-process (the guard resolves
        # in a SEPARATE process and would otherwise misread them). A cd also
        # moves the running cwd for later subcommands.
        run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': '/x/y/alpha',
                'tool_input': {'command': 'cd ../beta && git -C ../gamma log'},
            }
        )
        entries = json.loads(session.intent.read_text())
        assert {'path': '/x/y/beta', 'intent': True} in entries  # ../beta from /x/y/alpha
        # git -C ../gamma resolves against the new running cwd (/x/y/beta).
        assert {'path': '/x/y/gamma', 'intent': False} in entries

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


class TestTargetResolution:
    """worktree_create derives its target repo from the most-recent cd-intent
    (the leading signal), falling back to cwd only when none resolves. A pinned,
    stale cwd that disagrees with the intent no longer refuses — the worktree
    lands in the intent repo with a non-fatal stale-cwd note, so a pin-trapped
    session recovers with one cd."""

    def test_single_repo_session_creates(self, two_clones, session):
        tc = two_clones
        session.seed([{'path': str(tc.repo_a), 'intent': True}])
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_a / 'feat').is_dir()

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
        # Intent == cwd repo → no stale-cwd note.
        assert 'stale' not in result.stderr

    def test_mismatch_creates_in_intent_repo_and_warns(self, two_clones, session):
        tc = two_clones
        # Most-recent cd-intent is repo_b, but EnterWorktree cwd is the (stale)
        # repo_a. Target follows the intent: worktree lands in repo_b, with a
        # non-fatal stale-cwd note. This is the recovery the old guard refused.
        session.seed(
            [
                {'path': str(tc.repo_a), 'intent': True},
                {'path': str(tc.repo_b), 'intent': True},
            ]
        )
        # A gitignored env file in the INTENT clone must be the copy source — not
        # the stale cwd clone — since `source` follows the resolved target.
        (tc.repo_b / '.env').write_text('FROM=beta\n')
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_b / 'feat').is_dir()  # intent repo
        assert not (tc.wt_base / tc.name_a / 'feat').exists()  # NOT the stale cwd repo
        assert tc.name_b in result.stderr and 'stale' in result.stderr
        # Env-style files come from the intended (intent-derived) clone.
        assert (tc.wt_base / tc.name_b / 'feat' / '.env').read_text() == 'FROM=beta\n'

    def test_missing_intent_file_falls_through_to_cwd(self, two_clones, session):
        tc = two_clones
        # session.intent never seeded → unreadable state → fall back to cwd.
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_a / 'feat').is_dir()

    def test_missing_session_id_falls_through_to_cwd(self, two_clones):
        tc = two_clones
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a)}, env=tc.env)
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_a / 'feat').is_dir()

    def test_git_c_peek_into_other_repo_targets_cwd(self, two_clones, session):
        tc = two_clones
        # Real workflow: cd into the intended clone (repo_a), then a read-only
        # `git -C repo_b` peek. The peek is intent=False, so the most-recent
        # intent stays repo_a → worktree lands in repo_a, no stale-cwd note.
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
        assert (tc.wt_base / tc.name_a / 'feat').is_dir()
        assert 'stale' not in result.stderr

    def test_tracker_to_create_round_trip_targets_intent(self, two_clones, session):
        tc = two_clones
        # REAL writer→reader contract (not a hand-seeded file): the tracker
        # records cd into repo_a then cd into repo_b; EnterWorktree fires from the
        # stale repo_a cwd → target follows the most-recent intent (repo_b).
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
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_b / 'feat').is_dir()
        assert tc.name_b in result.stderr and 'stale' in result.stderr

    def test_relative_cd_intent_resolves_and_targets_intent(self, two_clones, session):
        tc = two_clones
        # Most-recent cd into repo_b expressed RELATIVELY. The tracker absolutizes
        # in-process, so the separate-process resolution still maps it to repo_b.
        rel_to_b = os.path.relpath(str(tc.repo_b), str(tc.repo_a))
        run_tracker_hook(
            {
                'tool_name': 'Bash',
                'session_id': session.id,
                'cwd': str(tc.repo_a),
                'tool_input': {'command': f'cd {rel_to_b}'},
            }
        )
        result = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert result.returncode == 0, result.stderr
        assert (tc.wt_base / tc.name_b / 'feat').is_dir()

    def test_idempotent_reentry_follows_resolved_target(self, two_clones, session):
        tc = two_clones
        # Create in repo_a with intent=repo_a, then re-enter the same name with
        # the same intent → the early-return returns the SAME path (never recreated).
        session.seed([{'path': str(tc.repo_a), 'intent': True}])
        first = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert first.returncode == 0, first.stderr
        second = run_create_hook({'name': 'feat', 'cwd': str(tc.repo_a), 'session_id': session.id}, env=tc.env)
        assert second.returncode == 0, second.stderr
        assert second.stdout.strip() == first.stdout.strip()


class TestResolveTargetUnit:
    """Direct unit coverage of resolve_target (no worktree creation)."""

    def test_intent_into_other_clone_overrides_cwd(self, two_clones, session):
        tc = two_clones
        session.seed([{'path': str(tc.repo_b), 'intent': True}])
        url, source = resolve_target(session.id, str(tc.repo_a))
        assert source == str(tc.repo_b)
        assert url == origin_url(str(tc.repo_b))

    def test_no_intent_falls_back_to_cwd(self, two_clones, session):
        tc = two_clones
        # No intent file → fallback to cwd's origin/path.
        url, source = resolve_target(session.id, str(tc.repo_a))
        assert source == str(tc.repo_a)
        assert url == origin_url(str(tc.repo_a))

    def test_intent_into_non_clone_is_skipped_walks_back(self, two_clones, session, tmp_path):
        tc = two_clones
        # Most-recent intent is a non-repo dir (clone_origin → None); the earlier
        # intent into repo_b is the first that resolves to a clone.
        non_repo = tmp_path / 'not-a-repo'
        non_repo.mkdir()
        session.seed(
            [
                {'path': str(tc.repo_b), 'intent': True},
                {'path': str(non_repo), 'intent': True},
            ]
        )
        url, source = resolve_target(session.id, str(tc.repo_a))
        assert source == str(tc.repo_b)
        assert url == origin_url(str(tc.repo_b))

    def test_no_origin_anywhere_returns_none(self, session, tmp_path):
        # cwd is not a repo and no valid intent → (None, cwd) so main()'s _err fires.
        not_repo = tmp_path / 'plain'
        not_repo.mkdir()
        url, source = resolve_target(session.id, str(not_repo))
        assert url is None
        assert source == str(not_repo)


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


class TestReadCloneWarn:
    """read_clone_warn.py: non-blocking warning when reading a clone with a worktree.

    Every outcome is `decision: approve`; the discriminating signal is the presence
    or absence of `systemMessage`, so the silent cases assert it is absent.
    """

    def _out(self, result):
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_warns_when_worktree_container_exists(self, remote_and_clone):
        rc = remote_and_clone
        # Materialize ~/wt/myrepo/ via the real create hook so paths line up.
        create = run_create_hook({'name': 'wt1', 'cwd': str(rc.clone)}, env=rc.env)
        assert create.returncode == 0, create.stderr

        clone_file = str(rc.clone / 'README.md')
        result = run_read_clone_hook(
            {'tool_name': 'Read', 'tool_input': {'file_path': clone_file}, 'cwd': str(rc.clone)},
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' in out
        assert rc.repo_name in out['systemMessage']
        assert clone_file in out['systemMessage']

    def test_silent_when_no_worktree_container(self, remote_and_clone):
        rc = remote_and_clone
        # No create hook → ~/wt/myrepo/ does not exist.
        result = run_read_clone_hook(
            {
                'tool_name': 'Read',
                'tool_input': {'file_path': str(rc.clone / 'README.md')},
                'cwd': str(rc.clone),
            },
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' not in out

    def test_silent_when_target_under_wt(self, remote_and_clone):
        rc = remote_and_clone
        create = run_create_hook({'name': 'wt2', 'cwd': str(rc.clone)}, env=rc.env)
        assert create.returncode == 0, create.stderr
        worktree = create.stdout.strip()

        result = run_read_clone_hook(
            {
                'tool_name': 'Read',
                'tool_input': {'file_path': os.path.join(worktree, 'README.md')},
                'cwd': worktree,
            },
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' not in out

    def test_silent_when_not_a_repo(self, remote_and_clone, tmp_path):
        rc = remote_and_clone
        loose = tmp_path / 'loose.txt'  # tmp_path itself is not a git repo
        loose.write_text('x\n')
        result = run_read_clone_hook(
            {'tool_name': 'Read', 'tool_input': {'file_path': str(loose)}, 'cwd': str(tmp_path)},
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' not in out

    def test_silent_when_disabled_in_config(self, remote_and_clone):
        rc = remote_and_clone
        create = run_create_hook({'name': 'wt3', 'cwd': str(rc.clone)}, env=rc.env)
        assert create.returncode == 0, create.stderr

        config_dir = rc.env['HOME'] + '/.config/claude-hooks'
        os.makedirs(config_dir, exist_ok=True)
        with open(config_dir + '/config.json', 'w') as f:
            json.dump({'read_clone_warn': False}, f)

        result = run_read_clone_hook(
            {
                'tool_name': 'Read',
                'tool_input': {'file_path': str(rc.clone / 'README.md')},
                'cwd': str(rc.clone),
            },
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' not in out

    def test_fail_open_on_malformed_input(self, remote_and_clone):
        result = run_read_clone_hook(None, env=remote_and_clone.env, raw='not valid json{')
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' not in out

    def test_grep_path_warns_when_worktree_exists(self, remote_and_clone):
        rc = remote_and_clone
        create = run_create_hook({'name': 'wt4', 'cwd': str(rc.clone)}, env=rc.env)
        assert create.returncode == 0, create.stderr

        result = run_read_clone_hook(
            {'tool_name': 'Grep', 'tool_input': {'pattern': 'Test', 'path': str(rc.clone)}, 'cwd': str(rc.clone)},
            env=rc.env,
        )
        out = self._out(result)
        assert out['decision'] == 'approve'
        assert 'systemMessage' in out
        assert rc.repo_name in out['systemMessage']


def _mk_bare_remote(tmp_path, remotes_dir, name):
    """A bare 'remote' with one commit, under `remotes_dir`. Returns its path."""
    src = tmp_path / f'src-{name}'
    src.mkdir()
    _git(['init', '-b', 'main'], src)
    _git(['config', 'user.email', 'test@test.com'], src)
    _git(['config', 'user.name', 'Test'], src)
    (src / 'README.md').write_text(f'# {name}\n')
    _git(['add', 'README.md'], src)
    _git(['commit', '-m', 'initial'], src)
    rem = remotes_dir / f'{name}.git'
    _git(['clone', '--bare', str(src), str(rem)], tmp_path)
    return rem


@pytest.fixture
def wt_on_demand(tmp_path):
    """A worktree base with one existing bare container ('existing') plus a second
    un-cloned remote ('newrepo') at the SAME url prefix — so org/host inference has
    a single clear winner and clone-on-demand can succeed. Both remotes live under
    `remotes/`, so a sibling-derived URL for 'newrepo' actually resolves."""
    remotes = tmp_path / 'remotes'
    remotes.mkdir()
    _mk_bare_remote(tmp_path, remotes, 'existing')
    _mk_bare_remote(tmp_path, remotes, 'newrepo')

    existing_clone = tmp_path / 'existing-clone'
    _git(['clone', str(remotes / 'existing.git'), str(existing_clone)], tmp_path)

    home = tmp_path / 'home'
    home.mkdir()
    wt_base = tmp_path / 'wt'
    env = {'CLAUDE_WORKTREE_BASE': str(wt_base), 'HOME': str(home)}
    # Bootstrap the 'existing' container so a sibling .bare exists to infer from.
    seed = run_create_hook({'name': 'seed', 'cwd': str(existing_clone)}, env=env)
    assert seed.returncode == 0, seed.stderr
    return SimpleNamespace(
        tmp_path=tmp_path,
        remotes=remotes,
        existing_clone=existing_clone,
        wt_base=wt_base,
        env=env,
    )


class TestWtRepoSegment:
    """wt_repo_segment: name a repo from a `cd ~/wt/<repo>` path (pure path math)."""

    def test_extracts_first_segment_under_base(self):
        base = Path('/home/u/wt')
        assert wt_repo_segment('/home/u/wt/apigw-lambdas', base) == 'apigw-lambdas'
        assert wt_repo_segment('/home/u/wt/apigw-lambdas/SRE-1', base) == 'apigw-lambdas'
        assert wt_repo_segment('/home/u/wt/apigw-lambdas/.bare', base) == 'apigw-lambdas'

    def test_none_at_base_off_base_or_dot_segment(self):
        base = Path('/home/u/wt')
        assert wt_repo_segment('/home/u/wt', base) is None
        assert wt_repo_segment('/home/u/code/foo', base) is None
        assert wt_repo_segment('/home/u/wt/.DS_Store', base) is None


class TestCloneUrlInference:
    """infer_clone_url: derive an on-demand clone URL from the environment (sibling
    containers under the worktree base) — never a hardcoded org/host."""

    def test_infers_single_winner_prefix(self, wt_on_demand):
        f = wt_on_demand
        assert infer_clone_url('newrepo', f.wt_base) == str(f.remotes / 'newrepo.git')

    def test_none_when_no_containers(self, tmp_path):
        empty = tmp_path / 'empty-wt'
        empty.mkdir()
        assert infer_clone_url('x', empty) is None

    def test_none_on_ambiguous_tie(self, tmp_path):
        base = tmp_path / 'wt'
        base.mkdir()
        # Two containers with DISTINCT url prefixes → 1-1 tie → no clear winner.
        for label, host in (('a', 'hostA'), ('b', 'hostB')):
            rem_dir = tmp_path / host
            rem_dir.mkdir()
            rem = _mk_bare_remote(tmp_path, rem_dir, label)
            cont = base / label
            _git(['clone', '--bare', str(rem), str(cont / '.bare')], tmp_path)
            (cont / '.git').write_text('gitdir: ./.bare\n')
        assert infer_clone_url('x', base) is None


class TestWtIntentResolution:
    """EnterWorktree from a `cd ~/wt/<repo>` intent: reuse the bare container,
    clone on demand, take precedence over a human clone, or ask when unresolvable."""

    def test_reuses_existing_bare_container(self, wt_on_demand, session):
        f = wt_on_demand
        session.seed([{'path': str(f.wt_base / 'existing'), 'intent': True}])
        # cwd is a non-repo dir → proves the target comes from the ~/wt intent.
        nonrepo = f.tmp_path / 'elsewhere'
        nonrepo.mkdir()
        r = run_create_hook({'name': 'feat', 'cwd': str(nonrepo), 'session_id': session.id}, env=f.env)
        assert r.returncode == 0, r.stderr
        assert (f.wt_base / 'existing' / 'feat').is_dir()

    def test_clones_on_demand_via_inference(self, wt_on_demand, session):
        f = wt_on_demand
        session.seed([{'path': str(f.wt_base / 'newrepo'), 'intent': True}])
        nonrepo = f.tmp_path / 'elsewhere2'
        nonrepo.mkdir()
        r = run_create_hook({'name': 'feat', 'cwd': str(nonrepo), 'session_id': session.id}, env=f.env)
        assert r.returncode == 0, r.stderr
        assert (f.wt_base / 'newrepo' / '.bare').is_dir()  # cloned on demand
        assert (f.wt_base / 'newrepo' / 'feat').is_dir()

    def test_wt_intent_takes_precedence_over_human_clone(self, wt_on_demand, session):
        f = wt_on_demand
        session.seed(
            [
                {'path': str(f.existing_clone), 'intent': True},  # older human clone
                {'path': str(f.wt_base / 'newrepo'), 'intent': True},  # newer ~/wt ref
            ]
        )
        r = run_create_hook({'name': 'feat', 'cwd': str(f.existing_clone), 'session_id': session.id}, env=f.env)
        assert r.returncode == 0, r.stderr
        assert (f.wt_base / 'newrepo' / 'feat').is_dir()

    def test_unresolvable_wt_intent_asks_rather_than_guessing(self, tmp_path, session):
        base = tmp_path / 'wt'
        base.mkdir()  # empty → nothing to infer from
        home = tmp_path / 'home'
        home.mkdir()
        env = {'CLAUDE_WORKTREE_BASE': str(base), 'HOME': str(home)}
        session.seed([{'path': str(base / 'mystery'), 'intent': True}])
        nonrepo = tmp_path / 'x'
        nonrepo.mkdir()
        r = run_create_hook({'name': 'feat', 'cwd': str(nonrepo), 'session_id': session.id}, env=env)
        assert r.returncode != 0
        assert 'mystery' in r.stderr
        assert 'Ask the user' in r.stderr

    def test_resolve_target_unit_unresolvable_returns_path_hint(self, tmp_path, session, monkeypatch):
        base = tmp_path / 'wt'
        base.mkdir()
        monkeypatch.setenv('CLAUDE_WORKTREE_BASE', str(base))
        monkeypatch.setenv('HOME', str(tmp_path / 'home'))
        session.seed([{'path': str(base / 'mystery'), 'intent': True}])
        nonrepo = tmp_path / 'x'
        nonrepo.mkdir()
        url, source = resolve_target(session.id, str(nonrepo))
        assert url is None
        assert source == str(base / 'mystery')  # carries the repo path for the ask


class TestFirstResearchWarn:
    """read_clone_warn fires on the FIRST research read of a repo with no worktree,
    but only when the ~/wt workflow is in use, and only once per repo per session."""

    def _out(self, result):
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_warns_first_read_when_workflow_in_use(self, wt_on_demand, session):
        f = wt_on_demand
        # Human clone of 'newrepo' — no container for it, but base has 'existing'.
        nc = f.tmp_path / 'newrepo-clone'
        _git(['clone', str(f.remotes / 'newrepo.git'), str(nc)], f.tmp_path)
        r = run_read_clone_hook(
            {'tool_name': 'Read', 'tool_input': {'file_path': str(nc / 'README.md')}, 'cwd': str(nc), 'session_id': session.id},
            env=f.env,
        )
        out = self._out(r)
        assert 'systemMessage' in out
        assert 'newrepo' in out['systemMessage']

    def test_deduped_once_per_session(self, wt_on_demand, session):
        f = wt_on_demand
        nc = f.tmp_path / 'newrepo-clone'
        _git(['clone', str(f.remotes / 'newrepo.git'), str(nc)], f.tmp_path)
        inp = {'tool_name': 'Read', 'tool_input': {'file_path': str(nc / 'README.md')}, 'cwd': str(nc), 'session_id': session.id}
        first = self._out(run_read_clone_hook(inp, env=f.env))
        second = self._out(run_read_clone_hook(inp, env=f.env))
        assert 'systemMessage' in first
        assert 'systemMessage' not in second  # cache suppresses the repeat

    def test_silent_when_workflow_not_in_use(self, tmp_path, session):
        # A human clone but an EMPTY worktree base → not a ~/wt user → no nudge.
        remotes = tmp_path / 'remotes'
        remotes.mkdir()
        rem = _mk_bare_remote(tmp_path, remotes, 'solo')
        clone = tmp_path / 'solo-clone'
        _git(['clone', str(rem), str(clone)], tmp_path)
        base = tmp_path / 'wt'
        base.mkdir()  # empty
        env = {'CLAUDE_WORKTREE_BASE': str(base), 'HOME': str(tmp_path / 'home')}
        (tmp_path / 'home').mkdir()
        r = run_read_clone_hook(
            {'tool_name': 'Read', 'tool_input': {'file_path': str(clone / 'README.md')}, 'cwd': str(clone), 'session_id': session.id},
            env=env,
        )
        out = self._out(r)
        assert 'systemMessage' not in out
