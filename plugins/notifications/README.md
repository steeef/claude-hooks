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

macOS only. Requires:

```bash
brew install jq terminal-notifier
```

- **jq** - Required for JSON parsing
- **terminal-notifier** - Required for desktop notifications (hook silently succeeds if missing)
