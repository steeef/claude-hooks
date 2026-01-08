"""Shared test fixtures for Claude hooks tests."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def make_hook_input():
    """Create hook input data structure."""

    def _make(tool_name, tool_input, **kwargs):
        return {'tool_name': tool_name, 'tool_input': tool_input, **kwargs}

    return _make


@pytest.fixture
def bash_input(make_hook_input):
    """Create Bash tool input."""

    def _make(command):
        return make_hook_input('Bash', {'command': command})

    return _make


@pytest.fixture
def write_input(make_hook_input):
    """Create Write tool input."""

    def _make(file_path, content):
        return make_hook_input('Write', {'file_path': file_path, 'content': content})

    return _make


@pytest.fixture
def edit_input(make_hook_input):
    """Create Edit tool input."""

    def _make(file_path, old_string, new_string, replace_all=False):
        return make_hook_input(
            'Edit',
            {
                'file_path': file_path,
                'old_string': old_string,
                'new_string': new_string,
                'replace_all': replace_all,
            },
        )

    return _make


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_dir = tmp_path / 'test_repo'
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=repo_dir, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=repo_dir, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo_dir, capture_output=True)

    # Create initial commit
    readme = repo_dir / 'README.md'
    readme.write_text('# Test Repo\n')
    subprocess.run(['git', 'add', 'README.md'], cwd=repo_dir, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo_dir, capture_output=True)

    original_cwd = os.getcwd()
    os.chdir(repo_dir)
    yield repo_dir
    os.chdir(original_cwd)


@pytest.fixture
def temp_non_git_dir(tmp_path):
    """Create a temporary directory that is NOT a git repo."""
    non_git_dir = tmp_path / 'non_git'
    non_git_dir.mkdir()

    original_cwd = os.getcwd()
    os.chdir(non_git_dir)
    yield non_git_dir
    os.chdir(original_cwd)


@pytest.fixture(autouse=True)
def cleanup_flag_files():
    """Clean up flag files before and after each test."""
    flag_file = Path('.claude_file_length_warning.flag')

    # Clean up before test
    if flag_file.exists():
        flag_file.unlink()

    yield

    # Clean up after test
    if flag_file.exists():
        flag_file.unlink()
