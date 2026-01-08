"""Tests for command-safety plugin."""

import subprocess
import sys
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'command-safety' / 'hooks'))


class TestRmCheck:
    """Tests for rm command checking with git-ignored file support."""

    def test_rm_blocks_tracked_file(self, bash_input, temp_git_repo):
        """rm on a tracked file should be blocked."""
        from rm_check import check_rm_command

        blocked, reason = check_rm_command('rm README.md')
        assert blocked is True
        assert 'TRASH' in reason or 'mv' in reason.lower()

    def test_rm_allows_git_ignored(self, bash_input, temp_git_repo):
        """rm on git-ignored files should be allowed."""
        from rm_check import check_rm_command

        # Create .gitignore and an ignored file
        gitignore = temp_git_repo / '.gitignore'
        gitignore.write_text('*.tmp\n.DS_Store\nnode_modules/\n')
        subprocess.run(['git', 'add', '.gitignore'], cwd=temp_git_repo)
        subprocess.run(['git', 'commit', '-m', 'add gitignore'], cwd=temp_git_repo)

        # Create an ignored file
        ignored_file = temp_git_repo / 'test.tmp'
        ignored_file.write_text('ignored content')

        blocked, reason = check_rm_command('rm test.tmp')
        assert blocked is False

    def test_rm_allows_ds_store(self, bash_input, temp_git_repo):
        """rm .DS_Store should be allowed (commonly ignored)."""
        from rm_check import check_rm_command

        # Create .gitignore with .DS_Store
        gitignore = temp_git_repo / '.gitignore'
        gitignore.write_text('.DS_Store\n')
        subprocess.run(['git', 'add', '.gitignore'], cwd=temp_git_repo)
        subprocess.run(['git', 'commit', '-m', 'add gitignore'], cwd=temp_git_repo)

        # Create .DS_Store
        ds_store = temp_git_repo / '.DS_Store'
        ds_store.write_text('')

        blocked, reason = check_rm_command('rm .DS_Store')
        assert blocked is False

    def test_rm_blocks_mixed_targets(self, bash_input, temp_git_repo):
        """rm with both ignored and tracked files should be blocked."""
        from rm_check import check_rm_command

        # Create .gitignore
        gitignore = temp_git_repo / '.gitignore'
        gitignore.write_text('.DS_Store\n')
        subprocess.run(['git', 'add', '.gitignore'], cwd=temp_git_repo)
        subprocess.run(['git', 'commit', '-m', 'add gitignore'], cwd=temp_git_repo)

        # Create files
        ds_store = temp_git_repo / '.DS_Store'
        ds_store.write_text('')

        blocked, reason = check_rm_command('rm .DS_Store README.md')
        assert blocked is True  # Should block because README.md is tracked

    def test_rm_handles_flags(self, bash_input, temp_git_repo):
        """rm -rf dir/ should correctly parse the directory path."""
        from rm_check import check_rm_command

        # Create .gitignore with node_modules
        gitignore = temp_git_repo / '.gitignore'
        gitignore.write_text('node_modules/\n')
        subprocess.run(['git', 'add', '.gitignore'], cwd=temp_git_repo)
        subprocess.run(['git', 'commit', '-m', 'add gitignore'], cwd=temp_git_repo)

        # Create node_modules directory
        node_modules = temp_git_repo / 'node_modules'
        node_modules.mkdir()
        (node_modules / 'package').mkdir()
        (node_modules / 'package' / 'index.js').write_text('')

        blocked, reason = check_rm_command('rm -rf node_modules/')
        assert blocked is False  # Should allow because node_modules is ignored

    def test_rm_outside_git_repo(self, bash_input, temp_non_git_dir):
        """rm outside a git repo should be blocked."""
        from rm_check import check_rm_command

        # Create a file outside git
        test_file = temp_non_git_dir / 'test.txt'
        test_file.write_text('test content')

        blocked, reason = check_rm_command('rm test.txt')
        assert blocked is True  # Should block all rm outside git repos


class TestKubectlCheck:
    """Tests for kubectl command safety."""

    def test_kubectl_blocks_delete(self, bash_input):
        """kubectl delete should be blocked."""
        from kubectl_check import check_kubectl_command

        decision, reason = check_kubectl_command('kubectl delete pod my-pod')
        assert decision == 'block'
        assert 'DESTRUCTIVE' in reason

    def test_kubectl_allows_get(self, bash_input):
        """kubectl get should be allowed."""
        from kubectl_check import check_kubectl_command

        decision, reason = check_kubectl_command('kubectl get pods')
        assert decision == 'allow'

    def test_kubectl_allows_dry_run(self, bash_input):
        """kubectl delete --dry-run should be allowed."""
        from kubectl_check import check_kubectl_command

        decision, reason = check_kubectl_command('kubectl delete pod my-pod --dry-run=client')
        assert decision == 'allow'

    def test_kubectl_blocks_apply(self, bash_input):
        """kubectl apply should be blocked."""
        from kubectl_check import check_kubectl_command

        decision, reason = check_kubectl_command('kubectl apply -f manifest.yaml')
        assert decision == 'block'


class TestTerraformCheck:
    """Tests for terraform command safety."""

    def test_terraform_blocks_destroy(self, bash_input):
        """terraform destroy should be blocked."""
        from terraform_check import check_terraform_command

        decision, reason = check_terraform_command('terraform destroy')
        assert decision == 'block'
        assert 'DESTRUCTIVE' in reason

    def test_terraform_blocks_apply(self, bash_input):
        """terraform apply should be blocked."""
        from terraform_check import check_terraform_command

        decision, reason = check_terraform_command('terraform apply')
        assert decision == 'block'

    def test_terraform_allows_plan(self, bash_input):
        """terraform plan should be allowed."""
        from terraform_check import check_terraform_command

        decision, reason = check_terraform_command('terraform plan')
        assert decision == 'allow'

    def test_terraform_allows_init(self, bash_input):
        """terraform init should be allowed."""
        from terraform_check import check_terraform_command

        decision, reason = check_terraform_command('terraform init')
        assert decision == 'allow'
