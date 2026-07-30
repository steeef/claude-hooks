"""Tests for gh-formatting plugin."""

import json
import subprocess
import sys
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'gh-formatting' / 'hooks'))

HOOK_SCRIPT = Path(__file__).parent.parent / 'plugins' / 'gh-formatting' / 'hooks' / 'gh_body_dewrap.py'

WRAPPED_PARAGRAPH = 'This is a paragraph that has been\nhard-wrapped across several lines\neven though it is really one thought.'
JOINED_PARAGRAPH = 'This is a paragraph that has been hard-wrapped across several lines even though it is really one thought.'


class TestExtractBodyFilePath:
    """Tests for detecting the gh command + its body file argument."""

    def test_pr_create_body_file(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh pr create --draft --title "x" --body-file /tmp/pr_body.md') == '/tmp/pr_body.md'

    def test_pr_edit_body_file(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh pr edit 123 --body-file /tmp/pr_body.md') == '/tmp/pr_body.md'

    def test_issue_comment_body_file(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh issue comment 42 --body-file /tmp/body.md') == '/tmp/body.md'

    def test_api_pulls_body_at_file(self):
        from gh_body_dewrap import extract_body_file_path

        cmd = 'gh api repos/o/r/pulls/123 -X PATCH -F body=@/tmp/pr_body.md'
        assert extract_body_file_path(cmd) == '/tmp/pr_body.md'

    def test_no_body_flag_is_none(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh pr view 123 --json body -q .body') is None

    def test_inline_body_is_none(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh pr create --body "inline text" --title x') is None

    def test_non_gh_command_is_none(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('cat --body-file /tmp/pr_body.md') is None

    def test_pr_view_pipe_is_none(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh pr view 123 --json body -q .body | head -5') is None


class TestDewrap:
    """Tests for the paragraph-rejoin logic."""

    def test_joins_wrapped_paragraph(self):
        from gh_body_dewrap import dewrap

        assert dewrap(WRAPPED_PARAGRAPH + '\n') == JOINED_PARAGRAPH + '\n'

    def test_preserves_fenced_code_block(self):
        from gh_body_dewrap import dewrap

        text = 'Intro line.\n\n```\nthis looks\nlike prose\nbut is code\n```\n\nOutro line.\n'
        assert dewrap(text) == text

    def test_preserves_list(self):
        from gh_body_dewrap import dewrap

        text = '- item one\n- item two\n- item three\n'
        assert dewrap(text) == text

    def test_preserves_table(self):
        from gh_body_dewrap import dewrap

        text = '| a | b |\n| --- | --- |\n| 1 | 2 |\n'
        assert dewrap(text) == text

    def test_preserves_blockquote(self):
        from gh_body_dewrap import dewrap

        text = '> quoted line one\n> quoted line two\n'
        assert dewrap(text) == text

    def test_related_documents_shape_untouched(self):
        from gh_body_dewrap import dewrap

        text = (
            '## Related Documents\n\n'
            '### Implementation Plan\n'
            '- [2026-04-15-MINT-123-feature.md](https://github.com/org/thoughts/blob/sha/plans/x.md)\n\n'
            '### Tickets\n'
            '- [MINT-123](https://company.atlassian.net/browse/MINT-123)\n'
        )
        assert dewrap(text) == text

    def test_footer_not_merged_or_mistaken_for_frontmatter(self):
        from gh_body_dewrap import dewrap

        text = 'Some closing paragraph.\n\n---\n🤖 Created with Conductor\n'
        assert dewrap(text) == text

    def test_leading_frontmatter_left_alone(self):
        from gh_body_dewrap import dewrap

        text = '---\ntier: personal\n---\n\n' + WRAPPED_PARAGRAPH + '\n'
        expected = '---\ntier: personal\n---\n\n' + JOINED_PARAGRAPH + '\n'
        assert dewrap(text) == expected

    def test_no_paragraphs_is_noop(self):
        from gh_body_dewrap import dewrap

        text = '# Just a title\n'
        assert dewrap(text) == text

    def test_multiple_paragraphs_each_join_independently(self):
        from gh_body_dewrap import dewrap

        text = f'{WRAPPED_PARAGRAPH}\n\n{WRAPPED_PARAGRAPH}\n'
        expected = f'{JOINED_PARAGRAPH}\n\n{JOINED_PARAGRAPH}\n'
        assert dewrap(text) == expected


class TestMainEndToEnd:
    """Subprocess-level tests exercising the real hook stdin/stdout contract."""

    def _run(self, payload):
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    def test_rewrites_referenced_body_file(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')

        result = self._run(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': f'gh pr edit 123 --body-file {body_file}'},
            }
        )

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
        assert body_file.read_text() == JOINED_PARAGRAPH + '\n'

    def test_non_bash_tool_is_noop(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')

        result = self._run({'tool_name': 'Write', 'tool_input': {'file_path': str(body_file)}})

        assert result.returncode == 0
        assert body_file.read_text() == WRAPPED_PARAGRAPH + '\n'

    def test_command_without_body_flag_is_noop(self, tmp_path):
        result = self._run({'tool_name': 'Bash', 'tool_input': {'command': 'gh pr view 123 --json body -q .body | head -5'}})

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}

    def test_missing_file_does_not_error(self):
        result = self._run(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': 'gh pr edit 123 --body-file /nonexistent/pr_body.md'},
            }
        )

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
