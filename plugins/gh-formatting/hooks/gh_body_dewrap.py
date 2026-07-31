#!/usr/bin/env python3
"""Hook (matcher: Bash, both PreToolUse and PostToolUse) that mechanically
rejoins hard-wrapped prose paragraphs in a gh pr body file so GitHub doesn't
render column-wrapped lines as broken <br> fragments. Structured lines
(fenced code, lists, blockquotes, headers, table rows, thematic breaks, a
leading frontmatter block) are left alone; only runs of consecutive plain
prose lines get joined into one line.

PreToolUse rewrites the body file in place before the about-to-run gh
command reads it -- the common case, where the file was written in an
earlier, separate tool call.

PostToolUse covers the case where the file was written and submitted to gh
in the *same* Bash invocation (e.g. `python3 ... > body.md && gh pr edit
... --body-file body.md`): PreToolUse necessarily ran before that write
happened, so its fix was clobbered before gh ever read the file. PostToolUse
re-reads the file after the whole command has finished (so it now holds
whatever was actually submitted), and if it's still wrapped, dewraps it
locally and pushes a follow-up `gh pr edit` to correct the body that already
landed on GitHub -- then reports what happened via additionalContext so it's
never a silent fix.

Always exits 0 -- never blocks the tool call itself. Inline `--body "..."`
invocations have no file to rewrite and are intentionally left alone.
"""

import json
import re
import subprocess
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

# For building the PostToolUse correction command: where does the PR live?
PR_EDIT_TARGET_RE = re.compile(r'\bgh\s+pr\s+edit\s+(\S+)')
REPO_FLAG_RE = re.compile(r'(?:--repo|-R)(?:=|\s+)["\']?([^"\'\s]+)["\']?')
API_PULLS_RE = re.compile(r'\bgh\s+api\s+(?:repos/)?([^/\s]+)/([^/\s]+)/pulls/(\d+)')
PR_URL_RE = re.compile(r'https://github\.com/[^/\s]+/[^/\s]+/pull/\d+')


def extract_body_file_path(command):
    if not command or not GH_COMMAND_RE.search(command):
        return None
    m = BODY_PATH_RE.search(command)
    return m.group(1) if m else None


def extract_correction_target(command, stdout):
    """Determine the `gh pr edit` target (a PR number or URL) and an
    optional --repo value for a PostToolUse correction, from either the
    original command (edit/api forms carry the target already) or the
    command's own stdout (create prints the new PR's URL)."""
    m = API_PULLS_RE.search(command or '')
    if m:
        owner, repo, number = m.groups()
        return number, f'{owner}/{repo}'

    m = PR_EDIT_TARGET_RE.search(command or '')
    if m:
        repo_m = REPO_FLAG_RE.search(command)
        return m.group(1), (repo_m.group(1) if repo_m else None)

    m = PR_URL_RE.search(stdout or '')
    if m:
        return m.group(0), None

    return None, None


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


def run_pre(payload):
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

    return {'decision': 'approve'}


def run_post(payload):
    command = (payload.get('tool_input') or {}).get('command', '')
    path = extract_body_file_path(command)
    if not path:
        return {'decision': 'approve'}

    try:
        with open(path, encoding='utf-8', newline='') as f:
            current = f.read()
    except OSError:
        return {'decision': 'approve'}

    corrected = dewrap(current)
    if corrected == current:
        return {'decision': 'approve'}

    # Still wrapped after the command finished -- PreToolUse ran before a
    # write later in the same Bash call clobbered its fix. Rewrite locally
    # and push a follow-up correction so the PR body that already landed on
    # GitHub gets fixed too.
    try:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(corrected)
    except OSError:
        pass

    stdout = (payload.get('tool_output') or {}).get('stdout', '')
    target, repo = extract_correction_target(command, stdout)

    if not target:
        return {
            'decision': 'approve',
            'additionalContext': (
                f'gh-formatting: {path} was still hard-wrapped when gh read it '
                '(likely written and submitted to gh in the same Bash call) and '
                'has been rewritten locally, but the PR target could not be '
                f'determined automatically -- rerun `gh pr edit <number> --body-file {path}` '
                'to push the fix.'
            ),
        }

    argv = ['gh', 'pr', 'edit', target, '--body-file', path]
    if repo:
        argv += ['--repo', repo]

    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except OSError as exc:
        return {
            'decision': 'approve',
            'additionalContext': (
                f'gh-formatting: {path} was hard-wrapped when gh read it (combined '
                f'write+gh call). Auto-correction failed to run ({exc}) -- rerun: '
                f'{" ".join(argv)}'
            ),
        }

    if result.returncode != 0:
        return {
            'decision': 'approve',
            'additionalContext': (
                f'gh-formatting: {path} was hard-wrapped when gh read it (combined '
                f'write+gh call). Auto-correction command failed: {" ".join(argv)} -> '
                f'{result.stderr.strip()}'
            ),
        }

    return {
        'decision': 'approve',
        'additionalContext': (
            'gh-formatting: detected a hard-wrapped body that was written and '
            'submitted to gh in the same Bash call (the PreToolUse dewrap ran too '
            f'early to help). Auto-corrected by re-running `gh pr edit {target}` '
            'with the dewrapped body -- avoid combining the write and the gh call '
            'in one command next time.'
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({'decision': 'approve'}))
        return 0

    if payload.get('tool_name') != 'Bash':
        print(json.dumps({'decision': 'approve'}))
        return 0

    event = payload.get('hook_event_name')
    is_post = event == 'PostToolUse' or (event is None and 'tool_output' in payload)
    result = run_post(payload) if is_post else run_pre(payload)

    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
