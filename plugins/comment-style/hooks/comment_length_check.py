#!/usr/bin/env python3
"""
Comment Style Check

Blocks Write/Edit/MultiEdit operations that introduce a comment block
violating either rule:

1. More than one consecutive comment-only line (no multi-line paragraphs).
2. More than MAX_COMMENT_WORDS words once the marker is stripped.

Only whole-line ("comment-only") lines are checked -- trailing inline
comments are left alone to avoid false positives from string literals
that happen to contain a marker character (URLs, SQL, etc).
"""

import re

MAX_COMMENT_WORDS = 7

# Maps file extension -> single-line comment marker. Block comments
# (/* */, triple-quoted docstrings) are intentionally out of scope --
# see README for rationale.
LINE_COMMENT_MARKERS = {
    '.py': '#',
    '.sh': '#',
    '.bash': '#',
    '.zsh': '#',
    '.rb': '#',
    '.yaml': '#',
    '.yml': '#',
    '.toml': '#',
    '.nix': '#',
    '.pl': '#',
    '.r': '#',
    '.js': '//',
    '.mjs': '//',
    '.cjs': '//',
    '.ts': '//',
    '.tsx': '//',
    '.jsx': '//',
    '.go': '//',
    '.rs': '//',
    '.java': '//',
    '.c': '//',
    '.cpp': '//',
    '.cc': '//',
    '.h': '//',
    '.hpp': '//',
    '.kt': '//',
    '.swift': '//',
    '.scala': '//',
    '.cs': '//',
    '.sql': '--',
    '.lua': '--',
    '.hs': '--',
    '.lisp': ';',
    '.el': ';',
    '.clj': ';',
}

# First word after the marker that marks a tool directive, not prose --
# these are exempt from both rules.
PRAGMA_RE = re.compile(
    r'^(noqa|type:|pragma|eslint-disable|eslint-enable|pylint:|nosec|nolint'
    r'|prettier-ignore|istanbul|@ts-ignore|@ts-expect-error|shellcheck'
    r'|spdx-license-identifier)',
    re.IGNORECASE,
)

LICENSE_RE = re.compile(r'\b(copyright|license|spdx)\b', re.IGNORECASE)


def get_comment_marker(file_path: str) -> str | None:
    for ext, marker in LINE_COMMENT_MARKERS.items():
        if file_path.endswith(ext):
            return marker
    return None


def extract_new_text(tool_name: str, tool_input: dict) -> str:
    if tool_name == 'Write':
        return tool_input.get('content', '') or ''
    if tool_name == 'Edit':
        return tool_input.get('new_string', '') or ''
    if tool_name == 'MultiEdit':
        return '\n'.join(e.get('new_string', '') or '' for e in tool_input.get('edits', []))
    return ''


def _is_exempt(block_text: str, is_shebang: bool) -> bool:
    if is_shebang:
        return True
    if PRAGMA_RE.match(block_text.strip()):
        return True
    return bool(LICENSE_RE.search(block_text))


def find_comment_violation(text: str, marker: str) -> str | None:
    """Return a violation message for the first offending comment block, or None."""
    lines = text.splitlines()
    escaped = re.escape(marker)
    comment_line_re = re.compile(rf'^\s*{escaped}(.*)$')

    i = 0
    while i < len(lines):
        m = comment_line_re.match(lines[i])
        if m is None:
            i += 1
            continue

        block_start = i
        block_contents = [m.group(1)]
        j = i + 1
        while j < len(lines):
            m2 = comment_line_re.match(lines[j])
            if m2 is None:
                break
            block_contents.append(m2.group(1))
            j += 1

        is_shebang = block_start == 0 and marker == '#' and block_contents[0].startswith('!')
        block_text = ' '.join(c.strip() for c in block_contents).strip()

        if not _is_exempt(block_text, is_shebang):
            if len(block_contents) > 1:
                return (
                    f'Comment block at line {block_start + 1} spans {len(block_contents)} lines. '
                    f'Comment blocks must be a single line -- WHY only, ≤{MAX_COMMENT_WORDS} words.'
                )
            word_count = len(block_text.split())
            if word_count > MAX_COMMENT_WORDS:
                return (
                    f'Comment at line {block_start + 1} has {word_count} words '
                    f'(max {MAX_COMMENT_WORDS}): "{block_text}". '
                    'State the non-obvious WHY only -- not what/how the code does.'
                )

        i = j

    return None


def check_comment_style(data: dict) -> tuple[bool, str | None]:
    tool_name = data.get('tool_name')
    if tool_name not in ('Write', 'Edit', 'MultiEdit'):
        return False, None

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '') or ''

    marker = get_comment_marker(file_path)
    if marker is None:
        return False, None

    text = extract_new_text(tool_name, tool_input)
    if not text:
        return False, None

    violation = find_comment_violation(text, marker)
    if violation is None:
        return False, None

    return True, violation
