#!/usr/bin/env bash
# Default rm-block guidance handler for command-safety's rm_check.py.
#
# Receives the blocked target paths as argv (may be empty); must print
# guidance to stdout and exit 0. This default reproduces the plugin's
# original behavior: move blocked files to TRASH/ and log them.
#
# Override via CLAUDE_HOOKS_RM_HANDLER to point at your own script/program
# instead - e.g. one that wraps a dedicated archival tool.
set -euo pipefail

cat <<'EOF'
Instead of using 'rm':
- MOVE files using `mv` to the TRASH directory in the CURRENT folder (create it if needed)
- Add an entry in 'TRASH-FILES.md' in the current directory:

```
test_script.py - moved to TRASH/ - temporary test script
```

Note: rm is allowed for git-ignored files (e.g., .DS_Store, node_modules/).
EOF
