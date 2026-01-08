#!/usr/bin/env python3
"""
Unified PreToolUse hook for all git operations.

Imports and runs checks from sub-modules in priority order.
Returns the first blocking/asking result, or approve if all pass.
"""

import json
import sys

from command_utils import expand_command_aliases
from git_add_block import check_git_add_command
from git_branch_workflow import check_git_branch_workflow
from git_checkout_safety import check_git_checkout_command
from worktree_suggestion import check_worktree_suggestion


def main():
    data = json.load(sys.stdin)

    # Check if this is a Bash tool call
    tool_name = data.get('tool_name')
    if tool_name != 'Bash':
        print(json.dumps({'decision': 'approve'}))
        sys.exit(0)

    # Get the command being executed
    command = data.get('tool_input', {}).get('command', '')

    # Expand aliases first
    command = expand_command_aliases(command)

    # Run checks in order of priority (most restrictive first)
    # 1. git add blocking (hard blocks)
    blocked, reason = check_git_add_command(command)
    if blocked is True or blocked == 'block':
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
        sys.exit(0)

    # 2. git checkout safety (hard blocks for dangerous patterns)
    blocked, reason = check_git_checkout_command(command)
    if blocked:
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
        sys.exit(0)

    # 3. Branch workflow enforcement (can block or ask)
    decision, reason = check_git_branch_workflow(command)
    if decision == 'block':
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
        sys.exit(0)
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
        sys.exit(0)

    # 4. Worktree suggestion (just adds context, doesn't block)
    _, suggestion = check_worktree_suggestion(command)
    if suggestion:
        print(json.dumps({'decision': 'approve', 'additionalContext': suggestion}))
        sys.exit(0)

    # All checks passed
    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


if __name__ == '__main__':
    main()
