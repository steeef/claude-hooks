#!/usr/bin/env python3
"""
Unified PreToolUse hook for file protection.

Imports and runs checks from sub-modules.
Returns the first blocking result, or approve if all pass.
"""

import json
import sys

from file_length_check import check_file_length_limit
from worktree_check import check_worktree_edit


def main():
    data = json.load(sys.stdin)

    tool_name = data.get('tool_name')
    tool_input = data.get('tool_input', {})
    session_id = data.get('session_id')

    # 1. Worktree edit guard (deny-then-ask speed bump)
    decision, reason = check_worktree_edit(tool_name, tool_input, session_id)
    if decision in ('deny', 'ask'):
        print(
            json.dumps(
                {
                    'hookSpecificOutput': {
                        'hookEventName': 'PreToolUse',
                        'permissionDecision': decision,
                        'permissionDecisionReason': reason,
                    }
                }
            )
        )
        sys.exit(0)

    # 2. File length check
    blocked, reason = check_file_length_limit(data)
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

    # All checks passed
    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


if __name__ == '__main__':
    main()
