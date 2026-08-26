# comment-style

Blocks new/edited comments that violate the "why-only, ≤7 words, one line"
comment convention, before the edit lands.

## Hook

### PreToolUse: comment_hook.py

Runs on `Write`, `Edit`, and `MultiEdit`. Scans only the newly written/changed
text (`content` for Write, `new_string` for Edit/MultiEdit) for whole-line
comments in the target file's language, and denies the operation if either
rule is violated:

1. **Multi-line block** -- more than one consecutive comment-only line.
2. **Too long** -- more than 7 words once the marker is stripped.

Trailing inline comments (`code()  # note`) are intentionally not checked --
detecting a marker inside a string literal without a real parser is too
false-positive-prone.

## Scope

Line-comment languages (`#`, `//`, `--`, `;`) -- see `LINE_COMMENT_MARKERS`
in `comment_length_check.py` for the full extension list -- plus Python's
bare triple-quoted string statements (`"""..."""`/`'''...'''`), Python's
only block-comment idiom (docstrings included). A quote assigned to a
variable (`x = """..."""`) is not a comment and is left alone. C-style
block comments (`/* */`) are out of scope for now.

## Exemptions

A comment block is skipped entirely if it is:

- A shebang (`#!/usr/bin/env ...`) on the first line.
- A tool directive (`noqa`, `type:`, `pragma`, `eslint-disable`,
  `pylint:`, `nosec`, `@ts-ignore`, `SPDX-License-Identifier`, etc).
- A license/copyright header (contains "copyright", "license", or "spdx").

## Configuration

No configuration required. Loaded automatically by Claude Code when
`CLAUDE_HOOKS_DIR` points to the parent claude-hooks directory, or via
`/plugin install comment-style@steeef/claude-hooks`.
