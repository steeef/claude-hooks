"""Tests for file-protection plugin."""

import sys
import time
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'file-protection' / 'hooks'))


class TestClaudeMdCheck:
    """Tests for CLAUDE.md write protection."""

    def test_claude_md_blocks_write(self, write_input):
        """Writing to CLAUDE.md should be blocked."""
        from claude_md_check import check_claude_md_write

        decision, reason = check_claude_md_write('Write', {'file_path': 'CLAUDE.md', 'content': ''})
        assert decision == 'block'
        assert 'AGENTS.md' in reason

    def test_claude_md_blocks_edit(self, edit_input):
        """Editing CLAUDE.md should be blocked."""
        from claude_md_check import check_claude_md_write

        decision, reason = check_claude_md_write('Edit', {'file_path': '/project/CLAUDE.md', 'old_string': 'x', 'new_string': 'y'})
        assert decision == 'block'

    def test_claude_md_allows_other(self, write_input):
        """Writing to other files should be allowed."""
        from claude_md_check import check_claude_md_write

        decision, reason = check_claude_md_write('Write', {'file_path': 'README.md', 'content': ''})
        assert decision == 'allow'

    def test_claude_md_case_insensitive(self, write_input):
        """CLAUDE.md check should be case insensitive."""
        from claude_md_check import check_claude_md_write

        decision, reason = check_claude_md_write('Write', {'file_path': 'claude.md', 'content': ''})
        assert decision == 'block'


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


class TestWorktreeEditGuard:
    """Tests for worktree edit guard (deny-then-ask speed bump)."""

    def test_denies_first_edit_in_main_repo(self, temp_git_repo):
        """First edit in main repo should be denied, flag created."""
        from worktree_check import FLAG_FILE, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}
        decision, reason = check_worktree_edit('Edit', tool_input)
        assert decision == 'deny'
        assert 'EnterWorktree' in reason
        assert FLAG_FILE.exists()

    def test_asks_on_second_attempt(self, temp_git_repo):
        """Second edit (flag exists) should ask the user, flag cleared."""
        from worktree_check import FLAG_FILE, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}

        # First call → deny, creates flag
        decision1, _ = check_worktree_edit('Edit', tool_input)
        assert decision1 == 'deny'

        # Second call → ask, clears flag
        decision2, reason2 = check_worktree_edit('Edit', tool_input)
        assert decision2 == 'ask'
        assert 'worktree' in reason2.lower()
        assert not FLAG_FILE.exists()

    def test_cycle_resets_after_ask(self, temp_git_repo):
        """After ask clears the flag, next edit returns deny again."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}

        # deny → ask → deny
        d1, _ = check_worktree_edit('Edit', tool_input)
        assert d1 == 'deny'
        d2, _ = check_worktree_edit('Edit', tool_input)
        assert d2 == 'ask'
        d3, _ = check_worktree_edit('Edit', tool_input)
        assert d3 == 'deny'

    def test_expired_flag_resets_to_deny(self, temp_git_repo):
        """A stale flag (beyond TTL) should be treated as absent → deny."""
        import os

        from worktree_check import FLAG_FILE, FLAG_TTL_SECONDS, check_worktree_edit

        tool_input = {'file_path': str(temp_git_repo / 'foo.py')}

        # Create flag then backdate it beyond TTL
        FLAG_FILE.touch()
        stale_time = time.time() - FLAG_TTL_SECONDS - 60
        os.utime(FLAG_FILE, (stale_time, stale_time))

        decision, reason = check_worktree_edit('Edit', tool_input)
        assert decision == 'deny'
        assert 'EnterWorktree' in reason

    def test_allows_when_in_worktree(self, temp_git_worktree):
        """Editing inside a worktree should be allowed."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_git_worktree / 'bar.py')}
        decision, reason = check_worktree_edit('Edit', tool_input)
        assert decision == 'allow'
        assert reason is None

    def test_allows_for_non_git_files(self, temp_non_git_dir):
        """Editing outside any git repo should be allowed."""
        from worktree_check import check_worktree_edit

        tool_input = {'file_path': str(temp_non_git_dir / 'script.py')}
        decision, reason = check_worktree_edit('Write', tool_input)
        assert decision == 'allow'
        assert reason is None

    def test_allows_when_no_file_path(self):
        """Missing file_path in input should be allowed."""
        from worktree_check import check_worktree_edit

        decision, reason = check_worktree_edit('Edit', {})
        assert decision == 'allow'
        assert reason is None
