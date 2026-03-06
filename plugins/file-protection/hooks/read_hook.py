#!/usr/bin/env python3
"""
PreToolUse hook for Read tool protection.

Checks read length limits before allowing large file reads.
"""

import json
import sys

from read_length_check import check_read_length


def main():
    try:
        data = json.load(sys.stdin)

        should_block, reason = check_read_length(data)

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
        else:
            print(json.dumps({'decision': 'approve'}))

        sys.exit(0)

    except Exception as e:
        # On error, approve to avoid breaking Claude
        print(json.dumps({'decision': 'approve', 'error': str(e)}))
        sys.exit(0)


if __name__ == '__main__':
    main()
