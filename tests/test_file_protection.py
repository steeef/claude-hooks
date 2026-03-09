"""Tests for file-protection plugin."""

import sys
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'file-protection' / 'hooks'))


class TestFileLengthCheck:
    """Tests for file length limit enforcement."""

    def test_file_length_warns_large(self, write_input, tmp_path):
        """Writing >MAX_FILE_LINES should warn/block."""
        from file_length_check import check_file_length_limit

        # Create content with many lines
        large_content = '\n'.join([f'line {i}' for i in range(15000)])

        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': str(tmp_path / 'large.py'), 'content': large_content},
        }

        blocked, reason = check_file_length_limit(data)
        assert blocked is True
        assert 'limit' in reason.lower() or 'lines' in reason.lower()

    def test_file_length_allows_small(self, write_input, tmp_path):
        """Writing <MAX_FILE_LINES should be allowed."""
        from file_length_check import check_file_length_limit

        small_content = '\n'.join([f'line {i}' for i in range(100)])

        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': str(tmp_path / 'small.py'), 'content': small_content},
        }

        blocked, reason = check_file_length_limit(data)
        assert blocked is False

    def test_file_length_ignores_non_source(self, write_input, tmp_path):
        """Non-source files should not be checked."""
        from file_length_check import check_file_length_limit

        large_content = '\n'.join([f'line {i}' for i in range(15000)])

        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': str(tmp_path / 'data.json'), 'content': large_content},
        }

        blocked, reason = check_file_length_limit(data)
        assert blocked is False

    def test_file_length_checks_edit(self, edit_input, tmp_path):
        """Edit operations should also be checked."""
        from file_length_check import check_file_length_limit

        # Create a file first
        source_file = tmp_path / 'edit_test.py'
        source_file.write_text("# original\nprint('hello')\n")

        # Try to replace with large content
        large_content = '\n'.join([f'line {i}' for i in range(15000)])

        data = {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(source_file),
                'old_string': "# original\nprint('hello')\n",
                'new_string': large_content,
            },
        }

        blocked, reason = check_file_length_limit(data)
        assert blocked is True

    def test_file_length_speed_bump(self, write_input, tmp_path):
        """Second attempt after flag should be allowed (speed bump pattern)."""
        from file_length_check import check_file_length_limit

        large_content = '\n'.join([f'line {i}' for i in range(15000)])

        data = {
            'tool_name': 'Write',
            'tool_input': {'file_path': str(tmp_path / 'speedbump.py'), 'content': large_content},
        }

        # First call should block and create flag
        blocked1, reason1 = check_file_length_limit(data)
        assert blocked1 is True

        # Second call should allow (flag exists)
        blocked2, reason2 = check_file_length_limit(data)
        assert blocked2 is False

        # Flag should be cleared, so third call should block again
        blocked3, reason3 = check_file_length_limit(data)
        assert blocked3 is True


class TestReadLengthCheck:
    """Tests for read length limit enforcement."""

    def test_blocks_large_file_read(self, tmp_path):
        """Reading a file >500 lines without offset/limit should be blocked."""
        from read_length_check import check_read_length

        large_file = tmp_path / 'large.py'
        large_file.write_text('\n'.join(f'line {i}' for i in range(600)))

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': str(large_file)},
        }

        blocked, reason = check_read_length(data)
        assert blocked is True
        assert '500' in reason
        assert 'offset' in reason.lower()

    def test_allows_small_file_read(self, tmp_path):
        """Reading a file <=500 lines should be allowed."""
        from read_length_check import check_read_length

        small_file = tmp_path / 'small.py'
        small_file.write_text('\n'.join(f'line {i}' for i in range(100)))

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': str(small_file)},
        }

        blocked, reason = check_read_length(data)
        assert blocked is False

    def test_allows_read_with_offset(self, tmp_path):
        """Reading with offset parameter should be allowed regardless of size."""
        from read_length_check import check_read_length

        large_file = tmp_path / 'large.py'
        large_file.write_text('\n'.join(f'line {i}' for i in range(600)))

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': str(large_file), 'offset': 100},
        }

        blocked, reason = check_read_length(data)
        assert blocked is False

    def test_allows_read_with_limit(self, tmp_path):
        """Reading with limit parameter should be allowed regardless of size."""
        from read_length_check import check_read_length

        large_file = tmp_path / 'large.py'
        large_file.write_text('\n'.join(f'line {i}' for i in range(600)))

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': str(large_file), 'limit': 50},
        }

        blocked, reason = check_read_length(data)
        assert blocked is False

    def test_speed_bump_allows_retry(self, tmp_path):
        """Second attempt on same file should be allowed, flag cleared."""
        from read_length_check import check_read_length

        large_file = tmp_path / 'large.py'
        large_file.write_text('\n'.join(f'line {i}' for i in range(600)))

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': str(large_file)},
        }

        # First call should block
        blocked1, _ = check_read_length(data)
        assert blocked1 is True

        # Second call should allow (flag exists)
        blocked2, _ = check_read_length(data)
        assert blocked2 is False

        # Third call should block again (flag was cleared)
        blocked3, _ = check_read_length(data)
        assert blocked3 is True

    def test_allows_nonexistent_file(self):
        """Reading a nonexistent file should be allowed (graceful)."""
        from read_length_check import check_read_length

        data = {
            'tool_name': 'Read',
            'tool_input': {'file_path': '/tmp/does_not_exist_12345.py'},
        }

        blocked, reason = check_read_length(data)
        assert blocked is False


class TestWorktreeEditGuard:
    """Tests for worktree edit guard (deny-then-ask speed bump)."""

    def test_denies_first_edit_in_main_repo(self, temp_git_repo):
        """First edit in main repo should be denied, flag contains session_id."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        flag_path = temp_git_repo / FLAG_FILENAME
        assert decision == 'deny'
        assert 'EnterWorktree' in reason
        assert flag_path.exists()
        assert flag_path.read_text() == 'session-001'

    def test_asks_on_second_attempt(self, temp_git_repo):
        """Second edit (flag exists, same session) should ask the user, flag cleared."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        flag_path = temp_git_repo / FLAG_FILENAME

        # First call → deny, creates flag
        decision1, _ = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision1 == 'deny'

        # Second call → ask, clears flag
        decision2, reason2 = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision2 == 'ask'
        assert 'worktree' in reason2.lower()
        assert not flag_path.exists()

    def test_cycle_resets_after_ask(self, temp_git_repo):
        """After ask clears the flag, next edit returns deny again."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}

        # deny → ask → deny
        d1, _ = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert d1 == 'deny'
        d2, _ = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert d2 == 'ask'
        d3, _ = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert d3 == 'deny'

    def test_different_session_resets_to_deny(self, temp_git_repo):
        """A flag from a different session should be treated as invalid → deny + overwrite."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        flag_path = temp_git_repo / FLAG_FILENAME

        # Session A creates flag
        decision1, _ = check_worktree_edit('Edit', tool_input, session_id='session-A')
        assert decision1 == 'deny'
        assert flag_path.read_text() == 'session-A'

        # Session B sees stale flag → deny + overwrite with its own id
        decision2, reason2 = check_worktree_edit('Edit', tool_input, session_id='session-B')
        assert decision2 == 'deny'
        assert 'EnterWorktree' in reason2
        assert flag_path.read_text() == 'session-B'

        # Session B second call → ask
        decision3, reason3 = check_worktree_edit('Edit', tool_input, session_id='session-B')
        assert decision3 == 'ask'

    def test_allows_when_no_session_id(self, temp_git_repo):
        """Missing or None session_id should allow (graceful fallback)."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}

        # Explicit None
        decision, reason = check_worktree_edit('Edit', tool_input, session_id=None)
        assert decision == 'allow'
        assert reason is None

        # Default (no arg)
        decision, reason = check_worktree_edit('Edit', tool_input)
        assert decision == 'allow'
        assert reason is None

    def test_allows_when_in_worktree(self, temp_git_worktree):
        """Editing inside a worktree should be allowed."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_git_worktree / 'bar.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision == 'allow'
        assert reason is None

    def test_allows_for_non_git_files(self, temp_non_git_dir):
        """Editing outside any git repo should be allowed."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_non_git_dir / 'script.py')}
        decision, reason = check_worktree_edit('Write', tool_input, session_id='session-001')
        assert decision == 'allow'
        assert reason is None

    def test_denies_edit_in_subdirectory(self, temp_git_repo):
        """Edit to file in a subdirectory should be denied, flag placed at repo root."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        subdir = temp_git_repo / 'src'
        subdir.mkdir()
        tool_input = {'file_path': str(subdir / 'main.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-sub')
        assert decision == 'deny'
        assert 'EnterWorktree' in reason

        # Flag must land at repo root, not in the subdirectory
        flag_path = temp_git_repo / FLAG_FILENAME
        assert flag_path.exists()
        assert flag_path.read_text() == 'session-sub'
        assert not (subdir / FLAG_FILENAME).exists()

    def test_denies_edit_in_deeply_nested_subdirectory(self, temp_git_repo):
        """Edit to file in a deeply nested subdirectory should be denied."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        deep_dir = temp_git_repo / 'src' / 'lib' / 'utils'
        deep_dir.mkdir(parents=True)
        tool_input = {'file_path': str(deep_dir / 'deep.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-deep')
        assert decision == 'deny'
        assert 'EnterWorktree' in reason

        # Flag at repo root, not in nested dir
        flag_path = temp_git_repo / FLAG_FILENAME
        assert flag_path.exists()
        assert flag_path.read_text() == 'session-deep'

    def test_deny_then_ask_cycle_from_subdirectory(self, temp_git_repo):
        """Full deny->ask cycle should work when edits target subdirectory files."""
        from worktree_check import FLAG_FILENAME, check_worktree_edit

        subdir = temp_git_repo / 'src'
        subdir.mkdir()
        tool_input = {'file_path': str(subdir / 'app.py')}

        # Phase 1: deny
        d1, r1 = check_worktree_edit('Edit', tool_input, session_id='session-cycle')
        assert d1 == 'deny'
        assert 'EnterWorktree' in r1

        # Phase 2: ask (flag at repo root, edit targets subdir)
        d2, r2 = check_worktree_edit('Edit', tool_input, session_id='session-cycle')
        assert d2 == 'ask'
        assert 'worktree' in r2.lower()

        # Flag should be cleared
        flag_path = temp_git_repo / FLAG_FILENAME
        assert not flag_path.exists()

        # Cycle resets: next edit denied again
        d3, _ = check_worktree_edit('Edit', tool_input, session_id='session-cycle')
        assert d3 == 'deny'

    def test_allows_when_no_file_path(self):
        """Missing file_path in input should be allowed."""
        from worktree_check import check_worktree_edit

        decision, reason = check_worktree_edit('Edit', {}, session_id='session-001')
        assert decision == 'allow'
        assert reason is None

    def test_allowlisted_repo_allows_edit(self, temp_git_repo, monkeypatch):
        """Allowlisted repo should skip deny/ask entirely."""
        from worktree_check import check_worktree_edit

        repo_root = str(temp_git_repo.resolve())
        monkeypatch.setattr(
            'worktree_check.load_config',
            lambda: {'worktree_guard_allowlist': [repo_root]},
        )

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision == 'allow'
        assert reason is None

    def test_non_allowlisted_repo_still_denies(self, temp_git_repo, monkeypatch):
        """Non-matching allowlist entry should not bypass the guard."""
        from worktree_check import check_worktree_edit

        monkeypatch.setattr(
            'worktree_check.load_config',
            lambda: {'worktree_guard_allowlist': ['/some/other/repo']},
        )

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision == 'deny'
        assert 'EnterWorktree' in reason

    def test_allowlist_with_tilde_expansion(self, temp_git_repo, monkeypatch):
        """Tilde paths in allowlist should expand correctly."""
        import os

        from worktree_check import check_worktree_edit

        repo_root = str(temp_git_repo.resolve())
        home = os.path.expanduser('~')
        # Build a tilde path that resolves to the repo root
        tilde_path = repo_root.replace(home, '~', 1) if repo_root.startswith(home) else repo_root
        monkeypatch.setattr(
            'worktree_check.load_config',
            lambda: {'worktree_guard_allowlist': [tilde_path]},
        )

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision == 'allow'
        assert reason is None

    def test_missing_config_returns_empty(self, temp_git_repo, monkeypatch):
        """Missing config file should not crash; guard should still fire."""
        from worktree_check import check_worktree_edit

        monkeypatch.setattr('worktree_check.load_config', lambda: {})

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input, session_id='session-001')
        assert decision == 'deny'
        assert 'EnterWorktree' in reason
