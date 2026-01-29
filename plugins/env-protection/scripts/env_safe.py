#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
env-safe: Safe inspection of .env files without exposing secrets.

This CLI tool allows you to inspect .env files safely by:
- Listing variable names (without values)
- Checking if a specific variable exists
- Counting variables
- Validating syntax

Usage:
    env-safe list [-f FILE] [--status]
    env-safe check KEY [-f FILE]
    env-safe count [-f FILE]
    env-safe validate [-f FILE]

Examples:
    env-safe list                    # List all variable names in .env
    env-safe list --status           # List names with value status (set/empty)
    env-safe check API_KEY           # Check if API_KEY exists
    env-safe count                   # Count variables in .env
    env-safe validate                # Check .env syntax
"""

import argparse
import re
import sys
from pathlib import Path


def find_env_file(specified_file: str | None = None) -> Path | None:
    """Find the .env file to use."""
    if specified_file:
        path = Path(specified_file)
        if path.exists():
            return path
        return None

    # Default to .env in current directory
    default = Path('.env')
    if default.exists():
        return default
    return None


def parse_env_file(path: Path) -> list[tuple[str, str, int]]:
    """
    Parse an env file and return list of (key, value, line_number) tuples.

    Handles:
    - KEY=value
    - KEY="quoted value"
    - KEY='single quoted'
    - export KEY=value
    - Comments (#)
    - Empty lines
    """
    entries = []
    line_pattern = re.compile(
        r'^(?:export\s+)?'  # Optional export prefix
        r'([A-Za-z_][A-Za-z0-9_]*)'  # Variable name
        r'='  # Equals sign
        r'(.*)$'  # Value (everything after =)
    )

    with open(path) as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            match = line_pattern.match(line)
            if match:
                key = match.group(1)
                value = match.group(2)

                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                entries.append((key, value, line_num))

    return entries


def cmd_list(args):
    """List variable names from .env file."""
    path = find_env_file(args.file)
    if not path:
        file_desc = args.file or '.env'
        print(f'Error: {file_desc} not found', file=sys.stderr)
        return 1

    entries = parse_env_file(path)

    if not entries:
        print('No variables found')
        return 0

    for key, value, _ in entries:
        if args.status:
            status = 'set' if value else 'empty'
            print(f'{key} ({status})')
        else:
            print(key)

    return 0


def cmd_check(args):
    """Check if a variable exists in .env file."""
    path = find_env_file(args.file)
    if not path:
        file_desc = args.file or '.env'
        print(f'Error: {file_desc} not found', file=sys.stderr)
        return 1

    entries = parse_env_file(path)
    keys = {entry[0] for entry in entries}

    if args.key in keys:
        # Find the entry to report status
        for key, value, _ in entries:
            if key == args.key:
                status = 'set' if value else 'empty'
                print(f'{args.key}: exists ({status})')
                return 0
    else:
        print(f'{args.key}: not found')
        return 1


def cmd_count(args):
    """Count variables in .env file."""
    path = find_env_file(args.file)
    if not path:
        file_desc = args.file or '.env'
        print(f'Error: {file_desc} not found', file=sys.stderr)
        return 1

    entries = parse_env_file(path)
    count = len(entries)
    set_count = sum(1 for _, value, _ in entries if value)
    empty_count = count - set_count

    print(f'Total: {count} variables')
    print(f'  Set: {set_count}')
    print(f'  Empty: {empty_count}')

    return 0


def cmd_validate(args):
    """Validate .env file syntax."""
    path = find_env_file(args.file)
    if not path:
        file_desc = args.file or '.env'
        print(f'Error: {file_desc} not found', file=sys.stderr)
        return 1

    errors = []
    warnings = []

    line_pattern = re.compile(
        r'^(?:export\s+)?'
        r'([A-Za-z_][A-Za-z0-9_]*)'
        r'='
        r'(.*)$'
    )

    with open(path) as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            match = line_pattern.match(line)
            if not match:
                errors.append(f'Line {line_num}: Invalid syntax')
                continue

            key, value = match.groups()

            # Check for common issues
            if value.startswith(' ') or value.endswith(' '):
                warnings.append(f'Line {line_num}: {key} has leading/trailing spaces in value')

            # Check for unquoted values with spaces
            if ' ' in value and not ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
                warnings.append(f'Line {line_num}: {key} has unquoted value with spaces')

            # Check for mismatched quotes
            if (value.startswith('"') and not value.endswith('"')) or (value.startswith("'") and not value.endswith("'")):
                errors.append(f'Line {line_num}: {key} has mismatched quotes')

    if errors:
        print('Errors:')
        for error in errors:
            print(f'  {error}')

    if warnings:
        print('Warnings:')
        for warning in warnings:
            print(f'  {warning}')

    if not errors and not warnings:
        print(f'Valid: {path} has no syntax issues')
        return 0

    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(
        description='Safe inspection of .env files without exposing secrets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  env-safe list                    List all variable names
  env-safe list --status           List names with value status
  env-safe list -f .env.local      List from specific file
  env-safe check API_KEY           Check if API_KEY exists
  env-safe count                   Count variables
  env-safe validate                Check syntax
        """,
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # list command
    list_parser = subparsers.add_parser('list', help='List variable names')
    list_parser.add_argument('-f', '--file', help='Path to env file (default: .env)')
    list_parser.add_argument('--status', action='store_true', help='Show if value is set or empty')

    # check command
    check_parser = subparsers.add_parser('check', help='Check if variable exists')
    check_parser.add_argument('key', metavar='KEY', help='Variable name to check')
    check_parser.add_argument('-f', '--file', help='Path to env file (default: .env)')

    # count command
    count_parser = subparsers.add_parser('count', help='Count variables')
    count_parser.add_argument('-f', '--file', help='Path to env file (default: .env)')

    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate syntax')
    validate_parser.add_argument('-f', '--file', help='Path to env file (default: .env)')

    args = parser.parse_args()

    commands = {
        'list': cmd_list,
        'check': cmd_check,
        'count': cmd_count,
        'validate': cmd_validate,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
