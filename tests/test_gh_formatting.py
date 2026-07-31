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

    def test_issue_command_is_none(self):
        from gh_body_dewrap import extract_body_file_path

        assert extract_body_file_path('gh issue comment 42 --body-file /tmp/body.md') is None

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


class TestExtractCorrectionTarget:
    """Tests for determining the PR to fix up in the PostToolUse path."""

    def test_edit_command_number(self):
        from gh_body_dewrap import extract_correction_target

        target, repo = extract_correction_target('gh pr edit 350 --body-file /tmp/x.md', '')
        assert target == '350'
        assert repo is None

    def test_edit_command_with_repo_flag(self):
        from gh_body_dewrap import extract_correction_target

        cmd = 'gh pr edit 350 --repo tatari-tv/platform-templates --body-file /tmp/x.md'
        target, repo = extract_correction_target(cmd, '')
        assert target == '350'
        assert repo == 'tatari-tv/platform-templates'

    def test_api_pulls_command(self):
        from gh_body_dewrap import extract_correction_target

        cmd = 'gh api repos/tatari-tv/platform-templates/pulls/350 -X PATCH -F body=@/tmp/x.md'
        target, repo = extract_correction_target(cmd, '')
        assert target == '350'
        assert repo == 'tatari-tv/platform-templates'

    def test_create_command_uses_stdout_url(self):
        from gh_body_dewrap import extract_correction_target

        cmd = 'gh pr create --draft --title x --body-file /tmp/x.md'
        stdout = 'https://github.com/tatari-tv/platform-templates/pull/350\n'
        target, repo = extract_correction_target(cmd, stdout)
        assert target == 'https://github.com/tatari-tv/platform-templates/pull/350'
        assert repo is None

    def test_no_target_found(self):
        from gh_body_dewrap import extract_correction_target

        target, repo = extract_correction_target('gh pr create --body-file /tmp/x.md', '')
        assert target is None
        assert repo is None


class TestPostToolUseCorrection:
    """Subprocess-level tests for the combined-call auto-correction path."""

    def _run_post(self, payload, path=None, fake_gh_dir=None):
        env = None
        if fake_gh_dir is not None:
            import os

            env = dict(os.environ)
            env['PATH'] = f'{fake_gh_dir}:{env["PATH"]}'
        payload = {**payload, 'hook_event_name': 'PostToolUse'}
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
        )

    def _fake_gh(self, tmp_path, log_path):
        """A stand-in `gh` binary that records its argv instead of hitting
        the network, so the correction command can be asserted on without
        ever touching a real PR."""
        fake_gh_dir = tmp_path / 'fakebin'
        fake_gh_dir.mkdir()
        fake_gh = fake_gh_dir / 'gh'
        fake_gh.write_text(
            f'#!/usr/bin/env python3\nimport sys\nopen({str(log_path)!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")\nsys.exit(0)\n'
        )
        fake_gh.chmod(0o755)
        return fake_gh_dir

    def test_combined_call_still_wrapped_triggers_correction(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')
        log_path = tmp_path / 'gh_calls.log'
        fake_gh_dir = self._fake_gh(tmp_path, log_path)

        result = self._run_post(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': f'gh pr edit 350 --repo tatari-tv/platform-templates --body-file {body_file}'},
                'tool_output': {'stdout': ''},
            },
            fake_gh_dir=fake_gh_dir,
        )

        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out['decision'] == 'approve'
        assert 'auto-corrected' in out['additionalContext'].lower()
        # local file is fixed
        assert body_file.read_text() == JOINED_PARAGRAPH + '\n'
        # the fake gh was invoked with the corrective edit
        logged = log_path.read_text()
        assert 'pr edit 350' in logged
        assert '--repo tatari-tv/platform-templates' in logged
        assert str(body_file) in logged

    def test_create_command_corrects_via_stdout_url(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')
        log_path = tmp_path / 'gh_calls.log'
        fake_gh_dir = self._fake_gh(tmp_path, log_path)

        result = self._run_post(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': f'gh pr create --draft --title x --body-file {body_file}'},
                'tool_output': {'stdout': 'https://github.com/tatari-tv/platform-templates/pull/350\n'},
            },
            fake_gh_dir=fake_gh_dir,
        )

        assert result.returncode == 0
        logged = log_path.read_text()
        assert 'https://github.com/tatari-tv/platform-templates/pull/350' in logged
        assert str(body_file) in logged

    def test_already_correct_body_is_noop(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(JOINED_PARAGRAPH + '\n')
        log_path = tmp_path / 'gh_calls.log'
        fake_gh_dir = self._fake_gh(tmp_path, log_path)

        result = self._run_post(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': f'gh pr edit 350 --body-file {body_file}'},
                'tool_output': {'stdout': ''},
            },
            fake_gh_dir=fake_gh_dir,
        )

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
        assert not log_path.exists()

    def test_no_target_found_warns_without_gh_call(self, tmp_path):
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')
        log_path = tmp_path / 'gh_calls.log'
        fake_gh_dir = self._fake_gh(tmp_path, log_path)

        result = self._run_post(
            {
                'tool_name': 'Bash',
                'tool_input': {'command': f'gh pr create --body-file {body_file}'},
                'tool_output': {'stdout': ''},
            },
            fake_gh_dir=fake_gh_dir,
        )

        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out['decision'] == 'approve'
        assert 'could not be determined' in out['additionalContext']
        assert body_file.read_text() == JOINED_PARAGRAPH + '\n'
        assert not log_path.exists()

    def test_pretooluse_still_dispatches_without_event_name(self, tmp_path):
        """A payload with no hook_event_name and no tool_output key (the
        shape PreToolUse actually sends) must still take the pre path, not
        be misrouted to post."""
        body_file = tmp_path / 'pr_body.md'
        body_file.write_text(WRAPPED_PARAGRAPH + '\n')

        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(
                {
                    'tool_name': 'Bash',
                    'tool_input': {'command': f'gh pr edit 350 --body-file {body_file}'},
                }
            ),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
        assert body_file.read_text() == JOINED_PARAGRAPH + '\n'
