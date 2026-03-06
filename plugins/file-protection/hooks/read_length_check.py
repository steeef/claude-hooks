#!/usr/bin/env python3
"""
Read Length Check Hook

Blocks Read operations on files exceeding MAX_READ_LINES when no offset/limit
is specified. Uses a speed bump pattern: first attempt blocks with a warning,
second attempt (after user approval) proceeds.
"""

import hashlib
import os
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_READ_LINES = 500


def _flag_path(file_path: str, session_id: str) -> Path:
    """Return per-file, per-session flag path in /tmp."""
    key = f'{session_id}:{file_path}'
    file_hash = hashlib.md5(key.encode()).hexdigest()[:12]
    return Path(f'/tmp/.claude_read_length_{file_hash}.flag')


def check_read_length(data: dict) -> tuple[bool, str | None]:
    """
    Check if a Read operation targets a file exceeding MAX_READ_LINES
    without offset/limit parameters.

    Returns:
        (should_block, reason)
    """
    tool_name = data.get('tool_name')

    if tool_name != 'Read':
        return False, None

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    # Targeted reads (offset or limit set) are fine
    if tool_input.get('offset') is not None or tool_input.get('limit') is not None:
        return False, None

    # If file doesn't exist, let Claude handle the error
    if not file_path or not os.path.exists(file_path):
        return False, None

    session_id = data.get('session_id', '')

    # Count lines (early-stop once we exceed threshold)
    try:
        line_count = 0
        with open(file_path, encoding='utf-8', errors='replace') as f:
            for _ in f:
                line_count += 1
                if line_count > MAX_READ_LINES:
                    break
    except Exception:
        return False, None

    if line_count <= MAX_READ_LINES:
        return False, None

    # Speed bump pattern (session-scoped)
    flag = _flag_path(file_path, session_id)

    if flag.exists():
        flag.unlink()
        return False, None

    flag.touch()

    reason = f"""
**Large file read blocked (>{MAX_READ_LINES} lines).**

The file `{file_path}` exceeds {MAX_READ_LINES} lines.

**Suggestions:**
- Use `offset` and `limit` parameters to read a specific section
- Use the `Task` tool to delegate exploration of this file
- Use `Grep` to find the relevant section first

**Only retry this Read if you truly need the entire file contents.**
"""

    return True, reason
