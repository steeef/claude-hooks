#!/usr/bin/env python3
"""Blocks --no-verify on git commit/push."""

import shlex

from command_utils import extract_subcommands

NO_VERIFY_REASON = 'git commit/push must not use --no-verify. Fix the failing hook instead of skipping it.'


def check_no_verify(command: str) -> tuple[str, str | None]:
    """Returns (decision, reason)."""
    for subcmd in extract_subcommands(command):
        try:
            tokens = shlex.split(subcmd)
        except ValueError:
            continue
        if len(tokens) < 2 or tokens[0] != 'git':
            continue
        if tokens[1] == 'commit' and ('--no-verify' in tokens or '-n' in tokens):
            return ('block', NO_VERIFY_REASON)
        if tokens[1] == 'push' and '--no-verify' in tokens:
            return ('block', NO_VERIFY_REASON)

    return ('allow', None)
