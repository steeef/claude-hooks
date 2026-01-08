#!/usr/bin/env python3
"""
Unified PreToolUse hook for dangerous command safety.

Imports and runs checks from sub-modules.
Returns the first blocking result, or approve if all pass.
"""

import json
import sys

from kubectl_check import check_kubectl_command
from rm_check import check_rm_command
from terraform_check import check_terraform_command


def main():
    data = json.load(sys.stdin)

    # Check if this is a Bash tool call
    tool_name = data.get('tool_name')
    if tool_name != 'Bash':
        print(json.dumps({'decision': 'approve'}))
        sys.exit(0)

    # Get the command being executed
    command = data.get('tool_input', {}).get('command', '')

    # Run checks in order
    # 1. rm check (most common)
    blocked, reason = check_rm_command(command)
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

    # 2. kubectl check
    decision, reason = check_kubectl_command(command)
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

    # 3. terraform check
    decision, reason = check_terraform_command(command)
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

    # All checks passed
    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


if __name__ == '__main__':
    main()
