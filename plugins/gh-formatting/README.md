# gh-formatting

Rejoins hard-wrapped prose paragraphs in `gh` PR/issue body files before
`gh` submits them, so GitHub doesn't render column-wrapped lines as broken
`<br>` fragments.

## Hooks

### PreToolUse: gh_body_dewrap.py

Fires on every `Bash` tool call. No-ops unless the command is a
`gh pr {create,edit,comment}`, `gh issue {create,edit,comment}`, or
`gh api .../{pulls,issues}/...` invocation carrying `--body-file <path>` or
`-F body=@<path>`. When it matches, rewrites that file in place, joining
each run of consecutive plain prose lines into a single line ("one
paragraph = one line"). Fenced code blocks, lists, blockquotes, headers,
table rows, thematic breaks, and a leading YAML frontmatter block are left
untouched.

Never blocks — always approves the tool call. Inline `--body "..."`
invocations have no file to rewrite and are intentionally left alone.

## Requirements

Python 3.11+ (no third-party dependencies).
