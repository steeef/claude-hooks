# env-protection

Blocks access to `.env` files, preventing accidental exposure of sensitive environment variables.

## Why This Exists

`.env` files contain secrets like API keys, database credentials, and other sensitive configuration. AI coding assistants that read these files could:

1. **Accidentally expose secrets** in responses or logs
2. **Include secrets in generated code** or documentation
3. **Leak credentials** through conversation history

This plugin prevents direct access to `.env` files while providing a safe alternative for inspecting environment configuration.

## What Gets Blocked

### Bash Commands

Commands that would read `.env` file contents:

```bash
cat .env                    # Blocked
less .env.local             # Blocked
grep API_KEY .env           # Blocked
vim .env.production         # Blocked
head -n 5 .env              # Blocked
source .env                 # Blocked
. .env                      # Blocked (dot sourcing)
```

### Read Tool

Direct file reads of `.env` files:

```text
Read: .env                  # Blocked
Read: /path/to/.env.local   # Blocked
Read: .env.development      # Blocked
```

## What's Allowed

### Safe Operations

```bash
ls -la .env                 # Allowed (metadata only)
mv .env .env.backup         # Allowed (doesn't read contents)
cp .env .env.backup         # Allowed
touch .env                  # Allowed
git commit -m "update .env" # Allowed (just message text)
echo "update .env file"     # Allowed
```

### Template Files

Files meant to show the expected format without actual secrets:

```text
.env.example                # Allowed
.env.template               # Allowed
.env.sample                 # Allowed
.env.dist                   # Allowed
```

## Safe Alternative: env-safe CLI

Instead of reading `.env` files directly, use the `env-safe` CLI to inspect them safely.

### CLI Installation

The CLI is included in the plugin at `scripts/env_safe.py`. Run it with `uv`:

```bash
uv run plugins/env-protection/scripts/env_safe.py <command>
```

Or make it executable and run directly:

```bash
chmod +x plugins/env-protection/scripts/env_safe.py
./plugins/env-protection/scripts/env_safe.py <command>
```

### Commands

#### list - Show variable names

```bash
# List all variable names (without values)
env-safe list

# Show value status (set/empty)
env-safe list --status

# Use specific file
env-safe list -f .env.local
```

Example output:

```text
API_KEY (set)
DATABASE_URL (set)
DEBUG (set)
EMPTY_VAR (empty)
```

#### check - Verify variable exists

```bash
# Check if a variable exists
env-safe check API_KEY

# Check in specific file
env-safe check DATABASE_URL -f .env.production
```

Example output:

```text
API_KEY: exists (set)
```

#### count - Count variables

```bash
env-safe count
```

Example output:

```text
Total: 4 variables
  Set: 3
  Empty: 1
```

#### validate - Check syntax

```bash
env-safe validate
```

Example output (valid):

```text
Valid: .env has no syntax issues
```

Example output (with issues):

```text
Errors:
  Line 5: Invalid syntax
Warnings:
  Line 3: API_KEY has unquoted value with spaces
```

## Plugin Installation

Enable the plugin in your Claude Code settings:

```json
{
  "plugins": ["env-protection"]
}
```

Or install from the marketplace:

```bash
claude plugins install env-protection
```

## Configuration

No configuration needed. The plugin automatically blocks `.env` file access for Bash and Read tools.
