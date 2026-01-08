"""Tests for git-hooks plugin."""

import subprocess
import sys
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'git-hooks' / 'hooks'))


class TestGitAddBlock:
    """Tests for git add blocking logic."""

    def test_git_add_blocks_wildcard(self, bash_input):
        """git add *.py should be blocked."""
        from git_add_block import check_git_add_command

        blocked, reason = check_git_add_command('git add *.py')
        assert blocked is True
        assert 'Wildcard' in reason

    def test_git_add_blocks_all_flag(self, bash_input):
        """git add -A should be blocked."""
        from git_add_block import check_git_add_command

        blocked, reason = check_git_add_command('git add -A')
        assert blocked is True

    def test_git_add_blocks_dot(self, bash_input):
        """git add . should be blocked."""
        from git_add_block import check_git_add_command

        blocked, reason = check_git_add_command('git add .')
        assert blocked is True

    def test_git_add_allows_specific_file(self, bash_input, temp_git_repo):
        """git add README.md should be allowed (for new files)."""
        from git_add_block import check_git_add_command

        # Create a new file (untracked)
        new_file = temp_git_repo / 'new_file.txt'
        new_file.write_text('test content')

        blocked, reason = check_git_add_command('git add new_file.txt')
        assert blocked is False

    def test_git_add_allows_dry_run(self, bash_input):
        """git add --dry-run should be allowed."""
        from git_add_block import check_git_add_command

        blocked, reason = check_git_add_command('git add --dry-run .')
        assert blocked is False


class TestGitCheckoutSafety:
    """Tests for git checkout safety checks."""

    def test_git_checkout_warns_force(self, bash_input):
        """git checkout -f should be blocked."""
        from git_checkout_safety import check_git_checkout_command

        blocked, reason = check_git_checkout_command('git checkout -f')
        assert blocked is True
        assert 'DANGEROUS' in reason or 'force' in reason.lower()

    def test_git_checkout_warns_dot(self, bash_input):
        """git checkout . should be blocked."""
        from git_checkout_safety import check_git_checkout_command

        blocked, reason = check_git_checkout_command('git checkout .')
        assert blocked is True

    def test_git_checkout_allows_new_branch(self, bash_input, temp_git_repo):
        """git checkout -b should be allowed."""
        from git_checkout_safety import check_git_checkout_command

        blocked, reason = check_git_checkout_command('git checkout -b new-branch')
        assert blocked is False


class TestGitCommitBlock:
    """Tests for git commit workflow enforcement."""

    def test_git_commit_asks_permission(self, bash_input, temp_git_repo):
        """git commit should ask for permission."""
        from git_commit_block import check_git_commit_command

        decision, reason = check_git_commit_command("git commit -m 'test'")
        assert decision == 'ask'

    def test_git_commit_allows_other_commands(self, bash_input):
        """Non-commit commands should be allowed."""
        from git_commit_block import check_git_commit_command

        decision, reason = check_git_commit_command('git status')
        assert decision == 'allow'


class TestGitBranchWorkflow:
    """Tests for branch workflow enforcement."""

    def test_branch_workflow_blocks_commit_on_main(self, bash_input, temp_git_repo):
        """Commits on main should be blocked."""
        from git_branch_workflow import check_git_branch_workflow

        decision, reason = check_git_branch_workflow("git commit -m 'test'")
        assert decision == 'block'
        assert 'main' in reason.lower() or 'protected' in reason.lower()

    def test_branch_workflow_allows_commit_on_feature(self, bash_input, temp_git_repo):
        """Commits on feature branches should ask (not block)."""
        from git_branch_workflow import check_git_branch_workflow

        # Switch to a feature branch
        subprocess.run(['git', 'checkout', '-b', 'PROJ-123-feature'], cwd=temp_git_repo)

        decision, reason = check_git_branch_workflow("git commit -m 'test'")
        assert decision == 'ask'  # Should ask, not block

    def test_branch_workflow_warns_missing_jira(self, bash_input, temp_git_repo):
        """Branch creation without Jira prefix should warn."""
        from git_branch_workflow import check_git_branch_workflow

        decision, reason = check_git_branch_workflow('git checkout -b my-feature')
        assert decision == 'ask'
        assert 'Jira' in reason or 'JIRA' in reason


class TestWorktreeSuggestion:
    """Tests for worktree suggestion logic."""

    def test_worktree_suggestion_shown(self, bash_input, temp_git_repo):
        """Feature branch creation should suggest worktree."""
        from worktree_suggestion import check_worktree_suggestion

        decision, suggestion = check_worktree_suggestion('git checkout -b feature/new-thing')
        assert decision == 'allow'
        assert suggestion is not None
        assert 'worktree' in suggestion.lower()

    def test_worktree_no_suggestion_for_hotfix(self, bash_input, temp_git_repo):
        """Hotfix branches should not suggest worktree."""
        from worktree_suggestion import check_worktree_suggestion

        decision, suggestion = check_worktree_suggestion('git checkout -b hotfix/urgent-fix')
        assert decision == 'allow'
        assert suggestion is None


class TestAliasExpansion:
    """Tests for alias expansion in commands."""

    def test_alias_expansion(self, bash_input):
        """Aliases like gco should be expanded."""
        from command_utils import expand_alias

        # Note: This test depends on user's actual aliases
        # The function should return the command unchanged if no alias found
        result = expand_alias('git checkout')
        assert 'git checkout' in result


class TestCompoundCommands:
    """Tests for compound command handling."""

    def test_extract_subcommands(self, bash_input):
        """Compound commands should be split correctly."""
        from command_utils import extract_subcommands

        subcmds = extract_subcommands("cd /tmp && git add . && git commit -m 'msg'")
        assert len(subcmds) == 3
        assert subcmds[0] == 'cd /tmp'
        assert subcmds[1] == 'git add .'
        assert subcmds[2] == "git commit -m 'msg'"
