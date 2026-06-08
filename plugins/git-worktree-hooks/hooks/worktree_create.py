#!/usr/bin/env python3
"""WorktreeCreate hook: bare-container worktrees under ~/wt.

Claude does its file-modifying work in bare containers it owns, never in the
human's clones under ~/code/work or ~/code. On EnterWorktree this hook:

  1. Derives the repo name + clone URL from the current dir's `origin` remote
     (read-only — the human's clone is only inspected, never modified).
  2. Bootstraps a bare container at ~/wt/<repo>/ (clone --bare into .bare/, a
     `.git` file pointing at it, fetch refspec, initial fetch) if absent — the
     bare-repo-as-container layout, so every worktree is a peer with no
     privileged "main checkout". Base dir is $CLAUDE_WORKTREE_BASE or ~/wt.
  3. Creates (or idempotently reuses) a worktree at ~/wt/<repo>/<name>.
  4. Copies gitignored env-style files (e.g. .env) into the new worktree, since
     a fresh worktree only contains tracked files. Never overwrites.

Output contract: only the worktree path on stdout; logs/errors go to stderr.
"""

import contextlib
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# Sibling module in the same plugin (run as scripts, so the hooks dir is on
# sys.path). Mirrors git-hooks' `from command_utils import ...`. Single source
# of truth for the session intent file the cwd_tracker hook writes.
from cwd_tracker import intent_path

CONFIG_PATH = Path(os.path.expanduser('~/.config/claude-hooks/config.json'))
DEFAULT_INCLUDE_GLOBS = ['.env', '.env.*']


def _run(args, cwd=None):
    """Run a git/shell command, returning the CompletedProcess (never raises)."""
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _err(msg) -> NoReturn:
    print(json.dumps({'error': msg}), file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def worktree_base() -> Path:
    """Base dir for bare containers: $CLAUDE_WORKTREE_BASE or ~/wt."""
    base = os.environ.get('CLAUDE_WORKTREE_BASE') or os.path.expanduser('~/wt')
    return Path(base)


def origin_url(cwd: str) -> str | None:
    r = _run(['git', '-C', cwd, 'remote', 'get-url', 'origin'])
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def repo_name_from_url(url: str) -> str:
    """myrepo from git@github.com:acme/myrepo.git (or https://.../myrepo)."""
    name = url.rstrip('/').rsplit('/', 1)[-1].rsplit(':', 1)[-1]
    if name.endswith('.git'):
        name = name[:-4]
    return name


def toplevel(cwd: str) -> str | None:
    r = _run(['git', '-C', cwd, 'rev-parse', '--show-toplevel'])
    return r.stdout.strip() if r.returncode == 0 else None


def is_valid_git_dir(path: str) -> bool:
    return _run(['git', '-C', path, 'rev-parse', '--git-dir']).returncode == 0


def clone_origin(path: str) -> str | None:
    """Origin URL of `path` IFF it is a human clone: it has an `origin` remote
    AND its toplevel is NOT inside the bare-container base (~/wt). Returns None
    for non-repos, missing paths, originless repos, and ~/wt worktrees — i.e.
    the things that must not count toward multi-repo ambiguity."""
    top = toplevel(path)
    if not top:
        return None
    try:
        top_resolved = Path(top).resolve()
        base_resolved = worktree_base().resolve()
        if top_resolved == base_resolved or base_resolved in top_resolved.parents:
            return None
    except Exception:
        return None
    return origin_url(path)


def multi_repo_refusal(session_id: str | None, cwd: str, target_url: str) -> str | None:
    """Return a refusal message if this EnterWorktree is an ambiguous multi-repo
    call, else None (allow). Fail-open: any unreadable state → None.

    Ambiguous = the session touched ≥2 distinct human clones AND the most-recent
    explicit `cd`/`git -C` intent does not resolve to the cwd's repo. The cwd
    (→ target_url) is a lagging signal the harness residual-cwd-pin can hold
    stale; the cd-intent is the leading signal of where the agent means to be.
    When they disagree across a multi-repo session, the worktree is likely being
    created in the wrong repo — refuse and make the agent cd in explicitly."""
    if not session_id:
        return None
    try:
        entries = json.loads(intent_path(session_id).read_text())
        if not isinstance(entries, list):
            return None
    except Exception:
        return None

    # Resolve distinct tracked paths → clone origins. Git calls happen HERE,
    # once per creation (deduped per path), never per Bash call.
    origin_cache: dict[str, str | None] = {}

    def origin_of(p: str) -> str | None:
        if p not in origin_cache:
            origin_cache[p] = clone_origin(p)
        return origin_cache[p]

    distinct: set[str] = set()
    most_recent_intent: str | None = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        p = e.get('path')
        if not isinstance(p, str):
            continue
        origin = origin_of(p)
        if not origin:
            continue
        distinct.add(origin)
        if e.get('intent'):
            most_recent_intent = origin

    # Single clone (or none resolvable) → never ambiguous.
    if len(distinct) <= 1:
        return None
    # The agent's most-recent explicit cd-intent lands in the cwd's repo → it
    # just cd'd into the intended clone; unambiguous, allow.
    if most_recent_intent == target_url:
        return None

    others = sorted(repo_name_from_url(u) for u in distinct if u != target_url)
    target_name = repo_name_from_url(target_url)
    return (
        'WORKTREE GUARD: ambiguous multi-repo EnterWorktree refused.\n'
        '\n'
        f'This session touched {len(distinct)} distinct clones; the worktree '
        f"would be created in '{target_name}' (derived from the current "
        f'directory:\n  {cwd}\n)\n'
        'but your most recent cd/git -C intent does not point there. Other '
        f'repos touched this session: {", ".join(others)}.\n'
        '\n'
        'If you meant a different repo, the current directory is likely stale '
        '(a residual cwd pin). To proceed:\n'
        '  cd <the intended clone> && EnterWorktree   (cd immediately before)\n'
        'then retry. A fresh cd into the intended clone clears this guard.'
    )


def ref_exists(container: Path, ref: str) -> bool:
    return _run(['git', '-C', str(container), 'show-ref', '--verify', '--quiet', ref]).returncode == 0


def default_base_ref(container: Path) -> str:
    """Default branch as a remote ref usable by `worktree add`: origin/HEAD → main → master."""
    r = _run(['git', '-C', str(container), 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()  # e.g. "origin/main"
    for b in ('main', 'master'):
        if ref_exists(container, f'refs/remotes/origin/{b}'):
            return f'origin/{b}'
    return 'origin/main'


def bootstrap_bare_container(container: Path, url: str) -> None:
    """Idempotently create a bare container at `container`.

    Layout: a `.bare/` object store plus a `.git` *file* pointing at it, so the
    container is tool-compatible and every worktree under it is a peer.
    """
    bare = container / '.bare'
    if bare.is_dir():
        # Refresh origin refs so a new worktree branches off current
        # origin/HEAD; --prune drops branches deleted on the remote. Non-fatal:
        # stale refs are fine offline. (Re-entering an existing worktree returns
        # before this, so an in-progress checkout is never touched.)
        _run(['git', '-C', str(container), 'fetch', '--prune', 'origin'])
        return

    print(f'📦 Bootstrapping bare container: {bare}', file=sys.stderr)
    container.mkdir(parents=True, exist_ok=True)
    clone = _run(['git', 'clone', '--bare', url, str(bare)])
    if clone.returncode != 0:
        shutil.rmtree(bare, ignore_errors=True)
        _err(f'git clone --bare failed for {url}: {clone.stderr.strip()}')

    # A .git *file* (not dir) lets editors/LSPs walking upward find the repo
    # from inside any worktree, and is more tool-compatible than a bare .git dir.
    (container / '.git').write_text('gitdir: ./.bare\n')
    # `git clone --bare` omits the fetch refspec, so restore it then fetch, or
    # `git fetch` / `origin/*` refs would be empty.
    _run(['git', '-C', str(container), 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*'])
    fetch = _run(['git', '-C', str(container), 'fetch', 'origin'])
    if fetch.returncode != 0:
        _err(f'git fetch origin failed in bootstrapped container {container}: {fetch.stderr.strip()}')


def copy_includes(source_root: str | None, worktree_dir: Path) -> int:
    """Copy gitignored env-style files into the fresh worktree. Never overwrite.

    Globs come from ~/.config/claude-hooks/config.json `worktree_include`
    (default .env / .env.*). Source is `worktree_include_source` if set, else the
    dir the EnterWorktree call came from (a human clone or sibling worktree).
    Best-effort: failures are swallowed so they never block worktree creation.
    """
    config = load_config()
    globs = config.get('worktree_include', DEFAULT_INCLUDE_GLOBS)
    if not globs:
        return 0
    src = config.get('worktree_include_source')
    src_root = Path(os.path.expanduser(src)) if src else (Path(source_root) if source_root else None)
    if not src_root or not src_root.is_dir():
        return 0

    copied = 0
    for entry in sorted(src_root.iterdir()):
        if not entry.is_file():
            continue
        if not any(fnmatch.fnmatch(entry.name, g) for g in globs):
            continue
        dest = worktree_dir / entry.name
        if dest.exists():
            continue
        with contextlib.suppress(OSError):
            shutil.copy2(entry, dest)
            copied += 1
    if copied:
        print(f'📋 Copied {copied} env-style file(s) into worktree', file=sys.stderr)
    return copied


def add_worktree(container: Path, worktree_dir: Path, name: str) -> None:
    cdir = str(container)
    wt = str(worktree_dir)
    if ref_exists(container, f'refs/heads/{name}'):
        result = _run(['git', '-C', cdir, 'worktree', 'add', wt, name])
    elif ref_exists(container, f'refs/remotes/origin/{name}'):
        result = _run(['git', '-C', cdir, 'worktree', 'add', '-b', name, wt, f'origin/{name}'])
    else:
        base = default_base_ref(container)
        result = _run(['git', '-C', cdir, 'worktree', 'add', '-b', name, wt, base])
    if result.returncode != 0:
        _err(result.stderr.strip() or 'git worktree add failed')


def main():
    data = json.load(sys.stdin)
    name = data.get('name', '').strip()
    if not name:
        _err('missing required field: name')

    cwd = data.get('cwd', '.')

    url = origin_url(cwd)
    if not url:
        _err(
            "cannot determine repo: no 'origin' remote in the current directory. "
            'cd into a clone of the target repo (its origin URL is read to derive '
            'the bare container) before calling EnterWorktree.'
        )

    repo = repo_name_from_url(url)
    container = worktree_base() / repo
    worktree_dir = container / name

    # Idempotent re-entry: existing valid worktree → return it. Runs BEFORE the
    # ambiguity guard so correct re-entry is never refused.
    if worktree_dir.is_dir() and is_valid_git_dir(str(worktree_dir)):
        print(str(worktree_dir))
        return

    # Multi-repo guard: refuse creating a NEW worktree when the session's recent
    # cd-intent disagrees with this cwd's repo across ≥2 touched clones.
    refusal = multi_repo_refusal(data.get('session_id'), cwd, url)
    if refusal:
        _err(refusal)

    bootstrap_bare_container(container, url)
    add_worktree(container, worktree_dir, name)
    copy_includes(toplevel(cwd), worktree_dir)

    # Only the worktree path on stdout (Claude Code contract).
    print(str(worktree_dir))


if __name__ == '__main__':
    main()
