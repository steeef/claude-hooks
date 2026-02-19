#!/usr/bin/env python3
"""
Check Grep tool access to .env files.

Blocks grepping of .env files to prevent accidental leakage
of sensitive environment variables via pattern search.
"""

import os

# Safe .env file suffixes that don't contain secrets (templates/examples)
SAFE_SUFFIXES = {'.example', '.template', '.sample', '.dist'}

# Glob patterns that target .env files
_ENV_GLOB_PATTERNS = {'.env*', '*.env', '.env.*'}

BLOCK_REASON = (
    'Blocked: Searching .env files via Grep is not allowed to prevent exposure of secrets. '
    'Use env-safe CLI to safely inspect environment variables: '
    'env-safe list, env-safe check KEY, env-safe validate'
)


def _is_env_file(basename: str) -> bool:
    """Check if a basename represents a sensitive .env file."""
    basename = basename.lower()

    if not basename.startswith('.env'):
        return False

    # Exact .env
    if basename == '.env':
        return True

    # .env.SUFFIX patterns
    if basename.startswith('.env.'):
        suffix = basename[4:]  # everything after '.env'
        return suffix not in SAFE_SUFFIXES

    return False


def _glob_targets_env(glob_pattern: str) -> bool:
    """Check if a glob pattern would match sensitive .env files."""
    pattern = glob_pattern.strip().lower()

    # Known broad env-targeting globs
    if pattern in _ENV_GLOB_PATTERNS:
        return True

    # Strip recursive prefix(es) (e.g. **/.env* -> .env*) and re-check
    stripped = pattern
    while stripped.startswith('**/'):
        stripped = stripped[3:]
    if stripped != pattern:
        if stripped in _ENV_GLOB_PATTERNS:
            return True
        basename = os.path.basename(stripped)
        if _is_env_file(basename):
            return True

    # Literal .env filename in glob (e.g. ".env.local", ".env.production")
    # Extract the basename portion for evaluation
    basename = os.path.basename(pattern)
    if _is_env_file(basename):
        return True

    # Basename starting with .env and containing wildcards targets env files
    return basename.startswith('.env') and any(c in basename for c in '*?[')


def check_env_grep(path: str | None, glob_pattern: str | None) -> tuple[bool, str | None]:
    """
    Check if Grep tool parameters target .env files.

    Args:
        path: The path parameter from Grep tool input
        glob_pattern: The glob parameter from Grep tool input

    Returns:
        (should_block, reason) tuple.
    """
    # Coerce inputs — non-string values become empty string
    path = path if isinstance(path, str) else ''
    glob_pattern = glob_pattern if isinstance(glob_pattern, str) else ''

    # Check path parameter
    if path:
        basename = os.path.basename(path)
        if basename and _is_env_file(basename):
            return (True, BLOCK_REASON)

    # Check glob parameter
    if glob_pattern and _glob_targets_env(glob_pattern):
        return (True, BLOCK_REASON)

    return (False, None)
