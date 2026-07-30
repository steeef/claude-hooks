# claude-hooks

[![CI](https://github.com/steeef/claude-hooks/actions/workflows/ci.yml/badge.svg)](https://github.com/steeef/claude-hooks/actions/workflows/ci.yml)

Safety and automation hooks for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

## Plugins

| Plugin | Type | Purpose |
|--------|------|---------|
| **command-safety** | PreToolUse | Blocks dangerous commands (`rm`, `kubectl delete`, `terraform destroy`) |
| **git-hooks** | PreToolUse/PostToolUse | Enforces git safety (no commits to main, blocks dangerous checkout/add patterns) |
| **file-protection** | PreToolUse | Worktree edit guard, blocks edits to `CLAUDE.md`, warns on very large files |
| **env-protection** | PreToolUse | Blocks access to `.env` files, prevents accidental secret exposure |
| **notifications** | Stop/Notification | Desktop notifications on macOS |
| **gh-formatting** | PreToolUse | Rejoins hard-wrapped PR/issue body prose before `gh` submits it |

## Installation

### Via Claude Code Plugin System (Recommended)

1. Add this repository as a marketplace source:

```text
/plugin marketplace add steeef/claude-hooks
```

2. Install the plugins you want:

```text
/plugin install command-safety@steeef/claude-hooks
/plugin install git-hooks@steeef/claude-hooks
/plugin install file-protection@steeef/claude-hooks
/plugin install notifications@steeef/claude-hooks
```

### Manual Installation

<details>
<summary>Click to expand manual installation instructions</summary>

1. Clone the repository:

```bash
git clone https://github.com/steeef/claude-hooks.git
cd claude-hooks
```

2. Set the `CLAUDE_HOOKS_DIR` environment variable (add to your shell rc file):

```bash
export CLAUDE_HOOKS_DIR="$HOME/code/claude-hooks"
```

3. Configure hooks in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/command-safety/hooks/command_hook.py"
          },
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/git-hooks/hooks/git_pre_hook.py"
          }
        ]
      },
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/file-protection/hooks/file_hook.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/git-hooks/hooks/cleanup_hook.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/notifications/hooks/notification_hook.sh"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_HOOKS_DIR/plugins/notifications/hooks/notification_hook.sh"
          }
        ]
      }
    ]
  }
}
```

</details>

## Plugin Details

### command-safety

Blocks potentially destructive commands:

- `rm` on git-tracked files (allows removal of ignored files like build artifacts)
- `kubectl delete`, `kubectl scale --replicas=0`, `kubectl cordon`, `kubectl drain`
- `terraform destroy`

#### Customizing the rm guidance

When `rm` is blocked, the "what to do instead" guidance comes from a pluggable
**handler script**, not hardcoded text. By default that's the bundled
`plugins/command-safety/hooks/rm_handlers/trash_handler.sh`, which reproduces
this plugin's original behavior (move to `TRASH/`, log to `TRASH-FILES.md`).

To use a different tool instead, set `CLAUDE_HOOKS_RM_HANDLER` to the path of
your own executable:

```bash
export CLAUDE_HOOKS_RM_HANDLER="$HOME/.claude/hooks/my_rm_handler.sh"
```

Handler contract:

- Invoked as `<handler> <target1> <target2> ...` — the blocked target paths as argv (may be empty).
- Must print guidance text to stdout and exit `0`.
- That output becomes the "how to fix it" portion of the block message shown to Claude — describe your own tool's usage, recovery, and listing commands however you like.

If the configured handler is missing, non-executable, errors, times out (5s), or prints nothing, the hook falls back to the bundled default handler, then to a generic notice if even that fails — so a broken handler config never silently shows guidance for a tool you're not using.

### git-hooks

Enforces safe git workflows:

- **Blocks commits to main/master** - forces feature branch workflow (configurable allowlist)
- **Blocks dangerous checkout** - prevents `git checkout main -- file` overwrites
- **Blocks dangerous add patterns** - prevents `git add -A`, `--force` flags
- **Suggests worktrees** - recommends git worktrees for feature branches
- **Cleanup hook** - clears branch tracking state after commands

### file-protection

Protects important files and encourages worktree workflow:

- **Worktree edit guard** - deny-then-ask speed bump for edits outside a git worktree (tied to session_id, not a timer)
- **Blocks CLAUDE.md edits** - project instructions should be edited manually
- **Large file warning** - warns before editing files over 10,000 lines (speed bump pattern with flag file)

### env-protection

Prevents accidental exposure of secrets in `.env` files:

- **Blocks `.env` reads** - both Bash commands (`cat .env`, `grep .env`) and Read tool
- **Allows safe operations** - `ls`, `mv`, `cp`, `touch` on `.env` files
- **Allows templates** - `.env.example`, `.env.template`, `.env.sample`
- **Safe CLI** - `env-safe` script for inspecting variable names without values

### notifications

Desktop notifications on macOS using `osascript`:

- Triggers on `Stop` events (task completion)
- Triggers on `Notification` events

### gh-formatting

Rejoins hard-wrapped PR/issue body prose before `gh` submits it:

- Fires on `gh pr {create,edit,comment}`, `gh issue {create,edit,comment}`, and `gh api .../{pulls,issues}/...` calls that carry `--body-file <path>` or `-F body=@<path>`
- Rewrites the referenced file in place, joining hard-wrapped paragraphs into one line each
- Leaves fenced code, lists, blockquotes, headers, tables, and thematic breaks untouched
- Never blocks; inline `--body "..."` invocations (no file to rewrite) are left alone

## Development

Requirements: Python 3.11+

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -v

# Run pre-commit hooks
uvx --with pre-commit-uv pre-commit run --all-files
```

## Acknowledgments

Based on [pchalasani/claude-code-tools](https://github.com/pchalasani/claude-code-tools).

## License

MIT License - see [LICENSE](LICENSE) for details.
