#!/usr/bin/env python3
"""PreToolUse hook entrypoint for comment-style enforcement."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from comment_length_check import check_comment_style


def main():
    data = json.load(sys.stdin)

    blocked, reason = check_comment_style(data)

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

    print(json.dumps({'decision': 'approve'}))
    sys.exit(0)


if __name__ == '__main__':
    main()
