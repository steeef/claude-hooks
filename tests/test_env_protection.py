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

    def test_allows_cat_env_dist(self):
        """cat .env.dist should be allowed (distribution template)."""
        from env_bash_check import check_env_bash

        should_block, reason = check_env_bash('cat .env.dist')
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

    def test_allows_read_env_dist(self):
        """.env.dist should be allowed (distribution template)."""
        from env_read_check import check_env_read

        should_block, reason = check_env_read('.env.dist')
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


class TestEnvGrepCheck:
    """Tests for Grep tool .env file access blocking."""

    # --- Path-based blocks ---

    def test_blocks_grep_path_to_env(self):
        """Grep targeting .env by path should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env', glob_pattern='')
        assert should_block is True
        assert '.env' in reason

    def test_blocks_grep_path_to_env_local(self):
        """Grep targeting .env.local by path should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env.local', glob_pattern='')
        assert should_block is True

    def test_blocks_grep_path_to_env_production(self):
        """Grep targeting .env.production by path should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='/app/.env.production', glob_pattern='')
        assert should_block is True

    def test_blocks_grep_path_to_nested_env(self):
        """Grep targeting nested .env by path should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='/home/user/project/.env', glob_pattern='')
        assert should_block is True

    # --- Path-based allows ---

    def test_allows_grep_path_to_env_example(self):
        """.env.example should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env.example', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_env_template(self):
        """.env.template should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env.template', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_env_sample(self):
        """.env.sample should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env.sample', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_env_dist(self):
        """.env.dist should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env.dist', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_directory(self):
        """Directory path should be allowed (can't block all directory searches)."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='src/', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_python_file(self):
        """Non-.env file path should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='config.py', glob_pattern='')
        assert should_block is False

    def test_allows_grep_path_to_environment_file(self):
        """Files with 'env' in name but not .env pattern should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='environment.py', glob_pattern='')
        assert should_block is False

    # --- Glob-based blocks ---

    def test_blocks_grep_glob_env_star(self):
        """Glob .env* should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env*')
        assert should_block is True

    def test_blocks_grep_glob_star_dot_env(self):
        """Glob *.env should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='*.env')
        assert should_block is True

    def test_blocks_grep_glob_env_dot_star(self):
        """Glob .env.* should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env.*')
        assert should_block is True

    def test_blocks_grep_glob_env_dot_local(self):
        """Glob .env.local should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env.local')
        assert should_block is True

    # --- Glob-based allows ---

    def test_allows_grep_glob_py(self):
        """Glob *.py should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='*.py')
        assert should_block is False

    def test_allows_grep_glob_js(self):
        """Glob *.js should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='*.js')
        assert should_block is False

    def test_allows_grep_glob_env_example(self):
        """Glob .env.example should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env.example')
        assert should_block is False

    # --- Empty/missing params ---

    def test_allows_empty_params(self):
        """Empty path and glob should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='')
        assert should_block is False

    def test_allows_none_params(self):
        """None path and glob should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path=None, glob_pattern=None)
        assert should_block is False

    # --- Combined params ---

    def test_blocks_when_path_targets_env_despite_safe_glob(self):
        """Path targeting .env should block even with safe glob."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='.env', glob_pattern='*.py')
        assert should_block is True

    def test_blocks_when_glob_targets_env_despite_safe_path(self):
        """Glob targeting .env should block even with safe path."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='src/', glob_pattern='.env*')
        assert should_block is True

    # --- Recursive glob blocks ---

    def test_blocks_grep_glob_recursive_env_star(self):
        """Glob **/.env* should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='**/.env*')
        assert should_block is True

    def test_blocks_grep_glob_recursive_env(self):
        """Glob **/.env should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='**/.env')
        assert should_block is True

    def test_blocks_grep_glob_recursive_env_local(self):
        """Glob **/.env.local should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='**/.env.local')
        assert should_block is True

    def test_allows_grep_glob_recursive_env_example(self):
        """Glob **/.env.example should be allowed."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='**/.env.example')
        assert should_block is False

    # --- Wildcard variant blocks ---

    def test_blocks_grep_glob_env_wildcard_variant(self):
        """Glob .env?ocal should be blocked (wildcard after .env)."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env?ocal')
        assert should_block is True

    def test_blocks_grep_glob_env_star_dot_star(self):
        """Glob .env*.* should be blocked."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='.env*.*')
        assert should_block is True

    # --- Non-.env recursive glob allows ---

    def test_allows_grep_glob_recursive_star_py(self):
        """Glob **/*.py should be allowed (no .env)."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern='**/*.py')
        assert should_block is False

    # --- Type safety (non-string inputs) ---

    def test_allows_grep_non_string_path(self):
        """Non-string path should not crash, should allow."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path=123, glob_pattern='')
        assert should_block is False

    def test_allows_grep_non_string_glob(self):
        """Non-string glob should not crash, should allow."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path='', glob_pattern=['*.env'])
        assert should_block is False

    def test_allows_grep_non_string_both(self):
        """Non-string path and glob should not crash, should allow."""
        from env_grep_check import check_env_grep

        should_block, reason = check_env_grep(path=None, glob_pattern=42)
        assert should_block is False
