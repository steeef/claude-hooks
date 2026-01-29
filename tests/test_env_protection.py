"""Tests for env-protection plugin."""

import sys
from pathlib import Path

# Add the hooks directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'env-protection' / 'hooks'))


class TestEnvBashCheck:
    """Tests for bash command .env file access blocking."""

    def test_blocks_cat_env(self):
        """cat .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat .env')
        assert should_block is True
        assert '.env' in reason

    def test_blocks_cat_env_local(self):
        """cat .env.local should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat .env.local')
        assert should_block is True

    def test_blocks_cat_env_development(self):
        """cat .env.development should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat .env.development')
        assert should_block is True

    def test_blocks_less_env(self):
        """less .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('less .env')
        assert should_block is True

    def test_blocks_grep_env(self):
        """grep in .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('grep API_KEY .env')
        assert should_block is True

    def test_blocks_vim_env(self):
        """vim .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('vim .env')
        assert should_block is True

    def test_blocks_head_env(self):
        """head .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('head -n 5 .env')
        assert should_block is True

    def test_blocks_tail_env(self):
        """tail .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('tail .env')
        assert should_block is True

    def test_blocks_env_in_path(self):
        """cat /path/to/.env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat /home/user/project/.env')
        assert should_block is True

    def test_blocks_source_env(self):
        """source .env should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('source .env')
        assert should_block is True

    def test_blocks_dot_env(self):
        """. .env (dot sourcing) should be blocked."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('. .env')
        assert should_block is True

    def test_allows_git_commit_mentioning_env(self):
        """git commit with .env in message should be allowed."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('git commit -m "update .env docs"')
        assert should_block is False

    def test_allows_echo_env_filename(self):
        """echo mentioning .env should be allowed."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('echo "Remember to update .env"')
        assert should_block is False

    def test_allows_ls_command(self):
        """ls command should be allowed (doesn't read contents)."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('ls -la .env')
        assert should_block is False

    def test_allows_mv_env(self):
        """mv .env should be allowed (doesn't read contents)."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('mv .env .env.backup')
        assert should_block is False

    def test_allows_cp_env(self):
        """cp .env should be allowed (doesn't expose contents)."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cp .env .env.backup')
        assert should_block is False

    def test_allows_touch_env(self):
        """touch .env should be allowed."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('touch .env')
        assert should_block is False

    def test_allows_normal_command(self):
        """Normal commands should be allowed."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('npm install')
        assert should_block is False

    def test_allows_cat_other_file(self):
        """cat on non-.env file should be allowed."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat README.md')
        assert should_block is False

    def test_blocks_env_file_in_docker_compose(self):
        """Commands that expose .env through docker-compose env_file should be handled."""
        from env_bash_check import check_env_bash

        # Reading .env via docker-compose should be blocked
        should_block, reason = check_env_bash('docker-compose config')
        # This is tricky - docker-compose config can expose env vars
        # For now, we'll allow it as it's indirect
        assert should_block is False


class TestEnvReadCheck:
    """Tests for Read tool .env file access blocking."""

    def test_blocks_read_env(self):
        """.env file read should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env')
        assert should_block is True
        assert '.env' in reason

    def test_blocks_read_env_local(self):
        """.env.local file read should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.local')
        assert should_block is True

    def test_blocks_read_env_development(self):
        """.env.development file read should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.development')
        assert should_block is True

    def test_blocks_read_env_production(self):
        """.env.production file read should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.production')
        assert should_block is True

    def test_blocks_read_env_in_path(self):
        """Full path to .env should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('/home/user/project/.env')
        assert should_block is True

    def test_blocks_read_env_in_nested_path(self):
        """Nested path to .env should be blocked."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('/project/backend/.env.local')
        assert should_block is True

    def test_allows_read_env_example(self):
        """.env.example should be allowed (contains placeholders, not secrets)."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.example')
        assert should_block is False

    def test_allows_read_env_template(self):
        """.env.template should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.template')
        assert should_block is False

    def test_allows_read_env_sample(self):
        """.env.sample should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.sample')
        assert should_block is False

    def test_allows_read_readme(self):
        """Non-.env files should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('README.md')
        assert should_block is False

    def test_allows_read_python_file(self):
        """Python files should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('config.py')
        assert should_block is False

    def test_allows_read_file_with_env_in_name(self):
        """Files with 'env' in name but not .env pattern should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('environment.py')
        assert should_block is False

    def test_allows_read_dotenv_package(self):
        """dotenv package files should be allowed."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('python-dotenv/dotenv.py')
        assert should_block is False
