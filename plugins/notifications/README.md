# notifications

Desktop notification hooks for Claude Code using terminal-notifier.

## Hooks

### Stop: notification_hook.sh

Plays the "Hero" sound and shows a "Task Done" notification when Claude
completes a task.

### Notification: notification_hook.sh

Plays the "Submarine" sound and shows an "Input Requested" notification when
Claude needs user input.

## Requirements

Requires `terminal-notifier` to be installed:

```bash
brew install terminal-notifier
```

If terminal-notifier is not installed, the hook silently succeeds without
showing notifications.

## Configuration

No configuration required. The hooks are automatically loaded by Claude Code
when `CLAUDE_HOOKS_DIR` points to the parent claude-hooks directory.
