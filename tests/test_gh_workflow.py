"""Tests for gh-workflow plugin."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'gh-workflow' / 'hooks'))

HOOK_SCRIPT = Path(__file__).parent.parent / 'plugins' / 'gh-workflow' / 'hooks' / 'gh_pr_draft_gate.py'


class TestCheckGhPrDraft:
    """Unit tests against the check function directly."""

    def test_create_with_draft_flag(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr create --draft --title x --body y')
        assert decision == 'allow'
        assert reason is None

    def test_create_with_short_draft_flag(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr create -d --title x')
        assert decision == 'allow'

    def test_create_shorthand_cluster_is_not_recognized(self):
        """ponytail: shorthand clusters like -df (draft+fill) aren't parsed --
        only exact --draft/-d tokens count, so this is treated as missing
        --draft rather than misread as containing it."""
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr create -df --title x')
        assert decision == 'deny'
        assert '--draft' in reason

    def test_create_without_draft_is_denied(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr create --title x')
        assert decision == 'deny'
        assert '--draft' in reason

    def test_create_dry_run_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr create --dry-run --title x')
        assert decision == 'allow'

    def test_create_help_long_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr create --help')
        assert decision == 'allow'

    def test_create_help_short_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr create -h')
        assert decision == 'allow'

    def test_ready_bare_asks(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr ready')
        assert decision == 'ask'
        assert reason

    def test_ready_with_number_asks(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr ready 123')
        assert decision == 'ask'

    def test_ready_undo_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr ready 123 --undo')
        assert decision == 'allow'

    def test_ready_help_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr ready --help')
        assert decision == 'allow'

    def test_deny_wins_over_ask_in_compound_command(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr create --title x && gh pr ready 123')
        assert decision == 'deny'
        assert '--draft' in reason

    def test_multiline_command_still_caught(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('git push -u origin HEAD\ngh pr create --title x')
        assert decision == 'deny'

    def test_env_prefixed_command_still_caught(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('env GH_TOKEN=x gh pr create --title x')
        assert decision == 'deny'

    def test_quoted_operator_with_draft_is_allowed(self):
        """A quoted && inside --title breaks segment tokenizing; the raw
        fallback must still find --draft on the full original command."""
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr create --draft --title "fix: handle a && b"')
        assert decision == 'allow'

    def test_quoted_operator_without_draft_is_denied(self):
        """This is the fail-open regression: without draft, the raw
        fallback must still deny rather than silently allow."""
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, reason = check_gh_pr_draft('gh pr create --title "fix: handle a && b"')
        assert decision == 'deny'
        assert '--draft' in reason

    def test_gh_issue_create_is_unaffected(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh issue create --title x')
        assert decision == 'allow'

    def test_gh_pr_view_is_unaffected(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('gh pr view 123')
        assert decision == 'allow'

    def test_non_gh_command_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('echo hello')
        assert decision == 'allow'

    def test_empty_command_is_allowed(self):
        from gh_pr_draft_gate import check_gh_pr_draft

        decision, _ = check_gh_pr_draft('')
        assert decision == 'allow'


class TestMainEndToEnd:
    """Subprocess-level tests exercising the real hook stdin/stdout contract."""

    def _run(self, payload):
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    def test_create_without_draft_denies(self):
        result = self._run({'tool_name': 'Bash', 'tool_input': {'command': 'gh pr create --title x'}})

        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out['hookSpecificOutput']['permissionDecision'] == 'deny'
        assert '--draft' in out['hookSpecificOutput']['permissionDecisionReason']

    def test_create_with_draft_approves(self):
        result = self._run({'tool_name': 'Bash', 'tool_input': {'command': 'gh pr create --draft --title x'}})

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}

    def test_ready_asks(self):
        result = self._run({'tool_name': 'Bash', 'tool_input': {'command': 'gh pr ready 123'}})

        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out['hookSpecificOutput']['permissionDecision'] == 'ask'

    def test_non_bash_tool_is_noop(self):
        result = self._run({'tool_name': 'Write', 'tool_input': {'file_path': '/tmp/x', 'content': 'gh pr create'}})

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}

    def test_malformed_stdin_is_noop(self):
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input='not json',
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert json.loads(result.stdout) == {'decision': 'approve'}
