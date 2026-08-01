# gh-workflow

Enforces a draft-first PR workflow: PRs are always created as drafts, and
marking one ready for review is a deliberate, confirmed action.

## Hook

`gh_pr_draft_gate.py` runs on every `Bash` tool call (PreToolUse). It no-ops
unless the command contains a `gh pr create` or `gh pr ready` invocation.

### `gh pr create`

Denied unless the exact token `--draft` or `-d` is present (shorthand
clusters like `-df` aren't parsed and are treated as missing `--draft`).
`-h`/`--help` and `--dry-run` are always allowed, since neither actually
creates a PR.

### `gh pr ready`

Always asks for confirmation, since this transitions a PR out of draft.
`--undo` (which moves a PR *back* into draft) and `-h`/`--help` are allowed
without asking.

## Parsing notes

Compound commands are split on `&&`, `||`, `;`, newlines, `|`, and `&`, then
each piece is tokenized with `shlex`. If a quoted argument happens to contain
one of those characters (e.g. `--title "a && b"`), splitting can sever the
quote and `shlex` will fail to tokenize the resulting piece — when that
happens, the hook falls back to a regex-only check over the *original,
unsplit* command rather than allowing the command through.

This is a local safety net, not a hard security boundary: it doesn't expand
shell aliases the way `git-hooks` does, so a personal alias like
`ghpr='gh pr create'` bypasses it.

## Requirements

Python 3.11+ (no third-party dependencies).
