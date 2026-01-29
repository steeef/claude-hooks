#!/usr/bin/env python3
"""
Check bash commands for .env file access.

Blocks commands that would expose .env file contents to prevent
accidental leakage of sensitive environment variables.
"""

import re

# Commands that read/display file contents (should be blocked for .env)
CONTENT_READING_COMMANDS = {
    'cat',
    'less',
    'more',
    'head',
    'tail',
    'grep',
    'egrep',
    'fgrep',
    'rg',  # ripgrep
    'ag',  # silver searcher
    'ack',
    'vim',
    'vi',
    'nvim',
    'nano',
    'emacs',
    'code',  # VS Code
    'subl',  # Sublime
    'bat',  # bat (cat clone)
    'sed',
    'awk',
    'perl',
    'python',
    'ruby',
    'node',
    'source',  # Shell sourcing
    'xargs',
    'tee',
    'sort',
    'uniq',
    'cut',
    'paste',
    'diff',
    'wc',
}

# Commands that don't expose contents (metadata only)
SAFE_COMMANDS = {
    'ls',
    'mv',
    'cp',
    'rm',
    'touch',
    'chmod',
    'chown',
    'stat',
    'file',
    'mkdir',
    'git',  # Git commands handled separately
    'echo',
    'printf',
}

# Pattern to match .env files
ENV_FILE_PATTERN = re.compile(
    r"""
    (?:^|[/\s"'])           # Start of string, path separator, whitespace, or quote
    \.env                    # .env
    (?:                      # Optional suffix
        \.                   # Dot
        (?!example|template|sample|dist)  # Negative lookahead for safe suffixes
        [a-zA-Z0-9_-]+       # Environment name like local, development, production
    )?
    (?:[/\s"']|$)           # End with path separator, whitespace, quote, or end
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Pattern to extract the first command from a pipeline
FIRST_COMMAND_PATTERN = re.compile(r'^\s*(?:sudo\s+)?(\S+)')


def check_env_bash(command: str) -> tuple[bool, str | None]:
    """
    Check if a bash command attempts to read .env file contents.

    Args:
        command: The bash command string

    Returns:
        (should_block, reason) tuple. should_block is True if command should
        be blocked, reason contains the explanation.
    """
    if not command:
        return (False, None)

    # Check if command mentions .env files
    if not ENV_FILE_PATTERN.search(command):
        return (False, None)

    # Git commands with .env in commit messages should be allowed
    if command.strip().startswith('git '):
        # Allow git commit messages mentioning .env
        if '-m ' in command or '--message' in command:
            return (False, None)
        # Allow git add/rm/mv for .env files (doesn't read contents)
        if any(cmd in command for cmd in ['git add', 'git rm', 'git mv', 'git status', 'git diff']):
            return (False, None)
        # Block git show, git cat-file, etc. that could expose contents
        if any(cmd in command for cmd in ['git show', 'git cat-file']):
            return (
                True,
                'Blocked: Command would expose .env file contents. Use env-safe CLI to safely inspect environment variables.',
            )
        return (False, None)

    # Echo/printf just mentioning .env is fine (doesn't read the file)
    first_cmd_match = FIRST_COMMAND_PATTERN.match(command)
    if first_cmd_match:
        first_cmd = first_cmd_match.group(1).lower()

        # Safe commands that don't read contents
        if first_cmd in SAFE_COMMANDS:
            return (False, None)

        # Dot sourcing (. .env) should be blocked
        if first_cmd == '.':
            return (
                True,
                'Blocked: Sourcing .env file would expose sensitive environment variables. '
                'Use env-safe CLI to safely inspect environment variables.',
            )

        # Content-reading commands should be blocked
        if first_cmd in CONTENT_READING_COMMANDS:
            return (
                True,
                'Blocked: Command would expose .env file contents. Use env-safe CLI to safely inspect environment variables.',
            )

    # Check for piped commands that could expose .env
    # e.g., "cat .env | grep API"
    pipe_parts = command.split('|')
    for part in pipe_parts:
        part = part.strip()
        if not part:
            continue
        part_match = FIRST_COMMAND_PATTERN.match(part)
        if part_match:
            part_cmd = part_match.group(1).lower()
            if part_cmd in CONTENT_READING_COMMANDS and ENV_FILE_PATTERN.search(part):
                return (
                    True,
                    'Blocked: Command would expose .env file contents. Use env-safe CLI to safely inspect environment variables.',
                )

    return (False, None)
