# gh-formatting

Rejoins hard-wrapped prose paragraphs in `gh pr` body files before `gh`
submits them, so GitHub doesn't render column-wrapped lines as broken
`<br>` fragments.

## Hooks

Both hooks below run the same script, `gh_body_dewrap.py`; it dispatches on
`hook_event_name` (falling back to "does the payload have a `tool_output`
key" if that field is absent).

### PreToolUse

Fires on every `Bash` tool call. No-ops unless the command is a
`gh pr {create,edit}` or `gh api .../pulls/...` invocation carrying
`--body-file <path>` or `-F body=@<path>` (the latter is the Projects-classic
REST fallback used when `gh pr edit` fails). When it matches, rewrites that
file in place, joining each run of consecutive plain prose lines into a
single line ("one paragraph = one line"). Fenced code blocks, lists,
blockquotes, headers, table rows, thematic breaks, and a leading YAML
frontmatter block are left untouched.

This only helps when the body file was written in an *earlier, separate*
tool call. Inline `--body "..."` invocations have no file to rewrite and are
intentionally left alone.

### PostToolUse

Covers the case PreToolUse structurally can't: a body file written and
submitted to `gh` in the *same* Bash invocation (e.g. `python3 ... >
body.md && gh pr edit ... --body-file body.md`). PreToolUse necessarily runs
before that write happens, so its fix gets clobbered a moment later, before
`gh` ever reads the file.

PostToolUse re-reads the body file after the whole command has finished (so
it now holds whatever was actually submitted). If it's still hard-wrapped,
it rewrites the file locally and pushes a follow-up `gh pr edit` to correct
the body that already landed on GitHub -- determining the target PR from the
original command (`gh pr edit <number>`/`gh api .../pulls/<number>` already
carry it) or, for `gh pr create`, by parsing the PR URL out of the command's
own stdout. If no target can be determined, it leaves the local file fixed
and reports that a manual `gh pr edit --body-file <path>` is needed.

Either way it reports what happened via `additionalContext` -- this never
fixes something silently.

Never blocks -- always approves the tool call.

## Requirements

Python 3.11+ (no third-party dependencies).
