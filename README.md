# claude-hooks

[![CI](https://github.com/steeef/claude-hooks/actions/workflows/ci.yml/badge.svg)](https://github.com/steeef/claude-hooks/actions/workflows/ci.yml)

Safety and automation hooks for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

## Plugins

| Plugin | Type | Purpose |
|--------|------|---------|
| **command-safety** | PreToolUse | Blocks dangerous commands (`rm`, `kubectl delete`, `terraform destroy`) |
| **git-hooks** | PreToolUse/PostToolUse | Enforces git safety (no commits to main, blocks dangerous checkout/add patterns) |
| **file-protection** | PreToolUse | Blocks edits to `CLAUDE.md`, warns on very large files |
| **notifications** | Stop/Notification | Desktop notifications on macOS |

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

### git-hooks

Enforces safe git workflows:

- **Blocks commits to main/master** - forces feature branch workflow
- **Blocks dangerous checkout** - prevents `git checkout main -- file` overwrites
- **Blocks dangerous add patterns** - prevents `git add -A`, `--force` flags
- **Suggests worktrees** - recommends git worktrees for feature branches
- **Cleanup hook** - clears branch tracking state after commands

### file-protection

Protects important files:

- **Blocks CLAUDE.md edits** - project instructions should be edited manually
- **Large file warning** - warns before editing files over 10,000 lines (speed bump pattern with flag file)

### notifications

Desktop notifications on macOS using `osascript`:

- Triggers on `Stop` events (task completion)
- Triggers on `Notification` events

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
