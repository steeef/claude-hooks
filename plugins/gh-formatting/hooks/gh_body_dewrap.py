#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash) that mechanically rejoins hard-wrapped
prose paragraphs in a gh pr body file before the command that reads it
runs, so GitHub doesn't render column-wrapped lines as broken <br>
fragments. Structured lines (fenced code, lists, blockquotes, headers,
table rows, thematic breaks, a leading frontmatter block) are left alone;
only runs of consecutive plain prose lines get joined into one line.
Always exits 0 -- this never blocks, it only mutates the file the
about-to-run gh command will read. Inline `--body "..."` invocations have
no file to rewrite and are intentionally left alone.
"""

import json
import re
import sys

FENCE_RE = re.compile(r'^(```|~~~)')
HEADER_RE = re.compile(r'^\s{0,3}#{1,6}(\s|$)')
LIST_RE = re.compile(r'^\s*([-*+]|\d+[.)])(\s|$)')
BLOCKQUOTE_RE = re.compile(r'^\s*>')
THEMATIC_BREAK_RE = re.compile(r'^\s*(-{3,}|\*{3,}|_{3,})\s*$')

# gh pr create/edit --body-file, or the gh api .../pulls/... -F body=@ fallback
# conductor:pr's Step 10 uses when gh pr edit fails on the Projects-classic bug.
GH_COMMAND_RE = re.compile(r'\bgh\s+pr\s+(create|edit)\b|\bgh\s+api\s+\S*pulls\S*')
BODY_PATH_RE = re.compile(r'(?:--body-file(?:=|\s+)|(?:-F|--field)\s+body=@)["\']?([^"\'\s]+)["\']?')


def extract_body_file_path(command):
    if not command or not GH_COMMAND_RE.search(command):
        return None
    m = BODY_PATH_RE.search(command)
    return m.group(1) if m else None


def is_structured(line):
    return (
        line.strip() == ''
        or HEADER_RE.match(line) is not None
        or LIST_RE.match(line) is not None
        or BLOCKQUOTE_RE.match(line) is not None
        or THEMATIC_BREAK_RE.match(line) is not None
        or '|' in line
    )


def split_leading_frontmatter(lines):
    """Defensive only: conductor:pr's Step 10 already strips frontmatter
    before writing the body file this hook sees. Anchored to line 0 so the
    trailing `---` + attribution footer is never mistaken for an
    (unterminated) frontmatter open."""
    if not lines or lines[0].rstrip('\r') != '---':
        return [], lines
    for i in range(1, len(lines)):
        if lines[i].rstrip('\r') == '---':
            return lines[: i + 1], lines[i + 1 :]
    return [], lines


def dewrap(text):
    had_trailing_newline = text.endswith('\n')
    lines = text.split('\n')
    if had_trailing_newline:
        lines = lines[:-1]

    frontmatter, body_lines = split_leading_frontmatter(lines)
    out = list(frontmatter)
    buffer = []
    in_fence = False

    def flush():
        if buffer:
            out.append(' '.join(s.strip() for s in buffer).strip())
            buffer.clear()

    for line in body_lines:
        if FENCE_RE.match(line.strip()):
            flush()
            out.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
            continue
        if is_structured(line):
            flush()
            out.append(line)
            continue
        buffer.append(line)
    flush()

    result = '\n'.join(out)
    if had_trailing_newline:
        result += '\n'
    return result


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
    path = extract_body_file_path(command)
    if path:
        try:
            with open(path, encoding='utf-8', newline='') as f:
                original = f.read()
            rewritten = dewrap(original)
            if rewritten != original:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(rewritten)
        except OSError:
            pass

    print(json.dumps({'decision': 'approve'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
