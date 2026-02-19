#!/usr/bin/env python3
"""
Unified PreToolUse hook for .env file protection.

Imports and runs checks from sub-modules based on tool type.
Returns the first blocking result, or approve if all pass.
"""

import json
import os
import sys

# Ensure local modules are importable regardless of execution context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_bash_check import check_env_bash
from env_grep_check import check_env_grep
from env_read_check import check_env_read


def main():
    data = json.load(sys.stdin)

    tool_name = data.get('tool_name')
    tool_input = data.get('tool_input', {})

    # Route to appropriate check based on tool
    should_block = False
    reason = None

    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        should_block, reason = check_env_bash(command)
    elif tool_name == 'Read':
        file_path = tool_input.get('file_path', '')
        should_block, reason = check_env_read(file_path)
    elif tool_name == 'Grep':
        path = tool_input.get('path', '')
        glob_pattern = tool_input.get('glob', '')
        should_block, reason = check_env_grep(path, glob_pattern)

    if should_block:
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
