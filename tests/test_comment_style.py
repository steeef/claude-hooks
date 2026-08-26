"""Tests for comment-style plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'comment-style' / 'hooks'))

from comment_length_check import check_comment_style


def write_data(file_path, content):
    return {'tool_name': 'Write', 'tool_input': {'file_path': file_path, 'content': content}}


def edit_data(file_path, new_string):
    return {
        'tool_name': 'Edit',
        'tool_input': {'file_path': file_path, 'old_string': 'x', 'new_string': new_string},
    }


def multiedit_data(file_path, new_strings):
    return {
        'tool_name': 'MultiEdit',
        'tool_input': {
            'file_path': file_path,
            'edits': [{'old_string': 'x', 'new_string': s} for s in new_strings],
        },
    }


class TestCommentStyle:
    def test_allows_short_single_line_comment(self):
        data = write_data('script.py', '# quick fix for retry race\nprint(1)\n')
        blocked, reason = check_comment_style(data)
        assert blocked is False
        assert reason is None

    def test_blocks_comment_over_word_limit(self):
        data = write_data(
            'script.py',
            '# this comment definitely has way more than seven words in it\nprint(1)\n',
        )
        blocked, reason = check_comment_style(data)
        assert blocked is True
        assert 'words' in reason.lower()

    def test_blocks_multiline_comment_block(self):
        data = write_data(
            'script.py',
            '# first line\n# second line\nprint(1)\n',
        )
        blocked, reason = check_comment_style(data)
        assert blocked is True
        assert 'lines' in reason.lower()

    def test_allows_shebang(self):
        data = write_data('script.sh', '#!/usr/bin/env bash\necho hi\n')
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_allows_pragma_comment(self):
        data = write_data('script.py', 'import os  # noqa\nx = 1  # type: ignore\n')
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_allows_license_header(self):
        data = write_data(
            'script.py',
            '# Copyright 2026 Example Corp\n# SPDX-License-Identifier: MIT\nprint(1)\n',
        )
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_ignores_non_source_extension(self):
        data = write_data('notes.md', '# heading not a comment ' + 'word ' * 10)
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_checks_edit_new_string_only(self):
        data = edit_data('script.py', '# fine one liner')
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_edit_blocks_multiline_new_string(self):
        data = edit_data('script.js', '// line one\n// line two\nconst x = 1;')
        blocked, reason = check_comment_style(data)
        assert blocked is True
        assert 'lines' in reason.lower()

    def test_multiedit_checks_each_edit(self):
        data = multiedit_data(
            'script.py',
            ['# ok', '# still way too many words for this rule honestly'],
        )
        blocked, reason = check_comment_style(data)
        assert blocked is True
        assert 'words' in reason.lower()

    def test_different_markers_per_language(self):
        data = write_data('query.sql', '-- select all active users only please right now\nSELECT 1;')
        blocked, reason = check_comment_style(data)
        assert blocked is True
        assert 'words' in reason.lower()

    def test_ignores_trailing_inline_comment(self):
        data = write_data(
            'script.py',
            'x = 1  # this trailing comment has way more than seven words total\n',
        )
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_allows_empty_content(self):
        data = write_data('script.py', '')
        blocked, _ = check_comment_style(data)
        assert blocked is False

    def test_ignores_other_tools(self):
        data = {'tool_name': 'Read', 'tool_input': {'file_path': 'script.py'}}
        blocked, _ = check_comment_style(data)
        assert blocked is False
