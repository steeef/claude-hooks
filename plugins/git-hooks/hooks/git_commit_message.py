#!/usr/bin/env python3
"""Commit message subject-length and Claude/AI-mention checks."""

import re
import shlex

MAX_SUBJECT_LENGTH = 50

AI_MENTION_RE = re.compile(r'\bclaude\b|\bai\b', re.IGNORECASE)

# heredoc -m args carry the real message
HEREDOC_RE = re.compile(r"<<-?['\"]?(\w+)['\"]?\n(.*?)\n\1\b", re.DOTALL)

SUBJECT_LENGTH_REASON = 'Commit subject line is {length} characters (limit {limit}). Shorten the first line of the commit message.'
AI_MENTION_REASON = "Commit message mentions '{match}'. Commit messages must not reference Claude, Claude Code, or AI."


def _extract_message(command: str) -> str | None:
    """None means no -m present."""
    heredoc_match = HEREDOC_RE.search(command)
    if heredoc_match:
        return heredoc_match.group(2)

    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    messages = []
    i = 0
    while i < len(tokens):
        if tokens[i] in ('-m', '--message') and i + 1 < len(tokens):
            messages.append(tokens[i + 1])
            i += 2
        elif tokens[i].startswith('--message='):
            messages.append(tokens[i][len('--message=') :])
            i += 1
        else:
            i += 1
    return '\n'.join(messages) if messages else None


def check_commit_message(command: str) -> tuple[str, str | None]:
    """Returns (decision, reason)."""
    normalized = ' '.join(command.strip().split())
    if not normalized.startswith('git commit'):
        return ('allow', None)

    message = _extract_message(command)
    if not message:
        return ('allow', None)

    subject = message.split('\n', 1)[0].strip()
    if len(subject) > MAX_SUBJECT_LENGTH:
        return (
            'block',
            SUBJECT_LENGTH_REASON.format(length=len(subject), limit=MAX_SUBJECT_LENGTH),
        )

    match = AI_MENTION_RE.search(message)
    if match:
        return ('block', AI_MENTION_REASON.format(match=match.group(0)))

    return ('allow', None)
