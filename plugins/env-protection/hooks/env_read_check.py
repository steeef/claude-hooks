#!/usr/bin/env python3
"""
Check Read tool access to .env files.

Blocks reading of .env files to prevent accidental leakage
of sensitive environment variables.
"""

import os

# Safe .env file suffixes that don't contain secrets (templates/examples)
SAFE_SUFFIXES = {'.example', '.template', '.sample', '.dist'}


def check_env_read(file_path: str) -> tuple[bool, str | None]:
    """
    Check if a file path targets a .env file that should be protected.

    Args:
        file_path: The file path being read

    Returns:
        (should_block, reason) tuple. should_block is True if read should
        be blocked, reason contains the explanation.
    """
    if not file_path:
        return (False, None)

    # Get just the filename
    basename = os.path.basename(file_path).lower()

    # Check if it's a .env file
    if not basename.startswith('.env'):
        return (False, None)

    # Exact match for .env
    if basename == '.env':
        return (
            True,
            'Blocked: Reading .env files is not allowed to prevent exposure of secrets. '
            'Use env-safe CLI to safely inspect environment variables: '
            'env-safe list, env-safe check KEY, env-safe validate',
        )

    # Check for .env.SUFFIX patterns
    # e.g., .env.local, .env.development, .env.production
    if basename.startswith('.env.'):
        suffix = basename[4:]  # Get everything after '.env'

        # Allow safe suffixes (templates/examples)
        if suffix in SAFE_SUFFIXES:
            return (False, None)

        # Block actual environment files
        return (
            True,
            f'Blocked: Reading {basename} files is not allowed to prevent exposure of secrets. '
            'Use env-safe CLI to safely inspect environment variables: '
            'env-safe list, env-safe check KEY, env-safe validate',
        )

    return (False, None)
