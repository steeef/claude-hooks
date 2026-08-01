#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash) enforcing a draft-first PR workflow.

`gh pr create` must include --draft (PRs always start as drafts); `gh pr
ready` always asks for confirmation before transitioning a PR out of draft.

Splits compound commands on shell operators (&&, ||, ;, newline, |, &) and
scans each segment's tokens for the `gh pr create`/`gh pr ready` subsequence
anywhere in the token list (not just at position 0), so env-prefixed
invocations like `GH_TOKEN=x gh pr create` or multi-line bash are still
caught. If any segment can't be tokenized by shlex (most likely because
splitting on an operator cut through a quoted argument, e.g. `--title "a &&
b"`), parsing falls back to a regex-only check over the *original* full
command -- never a blanket allow, since that would turn any quoted operator
into a bypass.
"""

import json
import re
import shlex
import sys

SEGMENT_RE = re.compile(r'&&|\|\||;|\n|\||&')

HELP_TOKENS = {'-h', '--help'}

# ponytail: gh pr create's short flags can combine into shorthand clusters
# (e.g. -df for --draft --fill), and pflag's value-flag-swallows-cluster-
# remainder rule (-bd is body="d", not draft) makes parsing those correctly
# a lot more code than the case is worth -- nobody actually types clustered
# shorthand flags in practice. Only exact `--draft`/`-d` tokens count; a
# cluster like `-df` is treated as missing --draft (denied, not misread).

CREATE_REASON = (
    'gh pr create must include --draft. PRs are always created in draft '
    'mode first -- use `gh pr ready` (which asks for confirmation) to mark '
    'one ready for review.'
)
READY_REASON = 'gh pr ready transitions this PR out of draft. Confirm this is intentional before proceeding.'


def _has_draft_flag(tokens):
    return '--draft' in tokens or '-d' in tokens


def _find_subsequence(tokens, subsequence):
    n = len(subsequence)
    return any(tokens[i : i + n] == subsequence for i in range(len(tokens) - n + 1))


def _check_segment_tokens(tokens):
    """Check one already-tokenized segment. Returns (decision, reason) or None."""
    if _find_subsequence(tokens, ['gh', 'pr', 'create']):
        if HELP_TOKENS & set(tokens):
            return None
        if '--dry-run' in tokens:
            return None
        if _has_draft_flag(tokens):
            return None
        return ('deny', CREATE_REASON)

    if _find_subsequence(tokens, ['gh', 'pr', 'ready']):
        if HELP_TOKENS & set(tokens):
            return None
        if '--undo' in tokens:
            return None  # moves the PR back into draft -- the safe direction
        return ('ask', READY_REASON)

    return None


RAW_CREATE_RE = re.compile(r'\bgh\s+pr\s+create\b')
RAW_READY_RE = re.compile(r'\bgh\s+pr\s+ready\b')
RAW_DRAFT_RE = re.compile(r'(?:^|\s)(?:--draft|-d)(?:\s|$)')
RAW_UNDO_RE = re.compile(r'(?:^|\s)--undo(?:\s|$)')
RAW_HELP_RE = re.compile(r'(?:^|\s)(?:-h|--help)(?:\s|$)')
RAW_DRY_RUN_RE = re.compile(r'(?:^|\s)--dry-run(?:\s|$)')


def _check_raw(command):
    """Regex-only fallback over the full original command, used when
    splitting on shell operators produced a segment shlex couldn't
    tokenize (most likely because a quoted argument contains one of the
    split characters, e.g. `--title "a && b"`)."""
    if RAW_CREATE_RE.search(command):
        if RAW_HELP_RE.search(command) or RAW_DRY_RUN_RE.search(command):
            return ('allow', None)
        if RAW_DRAFT_RE.search(command):
            return ('allow', None)
        return ('deny', CREATE_REASON)

    if RAW_READY_RE.search(command):
        if RAW_HELP_RE.search(command):
            return ('allow', None)
        if RAW_UNDO_RE.search(command):
            return ('allow', None)
        return ('ask', READY_REASON)

    return ('allow', None)


def check_gh_pr_draft(command):
    """
    Check a (possibly compound) bash command for gh pr create/ready gating.
    Returns (decision, reason) where decision is 'allow', 'ask', or 'deny'.
    """
    if not command or 'gh' not in command:
        return ('allow', None)

    segments = [s.strip() for s in SEGMENT_RE.split(command) if s.strip()]

    tokenized_segments = []
    for segment in segments:
        try:
            tokenized_segments.append(shlex.split(segment))
        except ValueError:
            return _check_raw(command)

    deny_reason = None
    ask_reason = None
    for tokens in tokenized_segments:
        result = _check_segment_tokens(tokens)
        if result is None:
            continue
        decision, reason = result
        if decision == 'deny' and deny_reason is None:
            deny_reason = reason
        elif decision == 'ask' and ask_reason is None:
            ask_reason = reason

    if deny_reason:
        return ('deny', deny_reason)
    if ask_reason:
        return ('ask', ask_reason)
    return ('allow', None)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({'decision': 'approve'}))
        return 0

    if payload.get('tool_name') != 'Bash':
        print(json.dumps({'decision': 'approve'}))
        return 0

    command = (payload.get('tool_input') or {}).get('command', '')
    decision, reason = check_gh_pr_draft(command)

    if decision == 'deny':
        print(
            json.dumps(
                {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': 'deny',
                        'permissionDecisionReason': reason,
                    }
                }
            )
        )
    elif decision == 'ask':
        print(
            json.dumps(
                {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': 'ask',
                        'permissionDecisionReason': reason,
                    }
                }
            )
        )
    else:
        print(json.dumps({'decision': 'approve'}))

    return 0


if __name__ == '__main__':
    sys.exit(main())
