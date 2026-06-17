#!/usr/bin/env python3
"""WorktreeCreate hook: bare-container worktrees under ~/wt.

Claude does its file-modifying work in bare containers it owns, never in the
human's clones under ~/code/work or ~/code. On EnterWorktree this hook:

  1. Derives the repo name + clone URL from the most-recent `cd`-intent that
     resolves to a human clone (recorded by cwd_tracker.py before the harness can
     snap the cwd back), falling back to the current dir's `origin` remote when
     no such intent exists (read-only — the clone is only inspected). On a
     cwd/intent origin mismatch it prints a non-fatal stale-cwd note to stderr.
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


def wt_repo_segment(path: str, base: Path) -> str | None:
    """Repo name when `path` is `<base>/<repo>` or `<base>/<repo>/...`, else None.

    Lets a `cd ~/wt/<repo>` intent name the repo by path alone — before anything
    is checked out there — so EnterWorktree can reuse the bare container or clone
    on demand without a human clone present. Pure path math (no fs/git): compared
    via normpath to match how cwd_tracker stores intent paths. Dot-prefixed first
    segments (e.g. a stray `.DS_Store`) are rejected — repos are plain names."""
    try:
        p = os.path.normpath(path)
        b = os.path.normpath(str(base))
    except Exception:
        return None
    if p == b:
        return None
    prefix = b + os.sep
    if not p.startswith(prefix):
        return None
    seg = p[len(prefix) :].split(os.sep, 1)[0]
    if not seg or seg.startswith('.'):
        return None
    return seg


def _url_prefix(url: str) -> str | None:
    """Everything up to and including the separator before the repo name, so
    `<prefix><repo>.git` reconstructs a sibling's URL for a different repo.
    `git@github.com:acme/foo.git` → `git@github.com:acme/`; `https://h/acme/foo` →
    `https://h/acme/`. None if there is no path/host separator."""
    s = url.rstrip('/')
    if s.endswith('.git'):
        s = s[:-4]
    cut = max(s.rfind('/'), s.rfind(':'))
    return s[: cut + 1] if cut != -1 else None


def infer_clone_url(repo: str, base: Path) -> str | None:
    """Clone URL for `repo` inferred from the origins of existing sibling bare
    containers under `base` — i.e. derived from where we're actually running, not
    a hardcoded org/host. Uses the single most common prefix across siblings. None
    when there is no sibling origin to mirror OR no clear winner (a tie at the top
    is "can't figure it out" → caller asks rather than guessing)."""
    try:
        dirs = [d for d in base.iterdir() if (d / '.bare').is_dir()]
    except Exception:
        return None
    counts: dict[str, int] = {}
    for d in dirs:
        url = origin_url(str(d))
        prefix = _url_prefix(url) if url else None
        if prefix:
            counts[prefix] = counts.get(prefix, 0) + 1
    if not counts:
        return None
    top = max(counts.values())
    winners = [p for p, n in counts.items() if n == top]
    if len(winners) != 1:
        return None  # ambiguous org/host — don't guess
    return f'{winners[0]}{repo}.git'


def resolve_target(session_id: str | None, cwd: str) -> tuple[str | None, str | None]:
    """(origin_url, source_clone_path) for the worktree to create.

    Prefer the most-recent explicit `cd`-intent, recorded by cwd_tracker.py before
    the harness can snap the cwd back (the leading signal of where the agent means
    to be). Two kinds of intent resolve a target, most-recent first:

      1. A `cd ~/wt/<repo>` intent — names the repo by path. Reuses the existing
         bare container's origin, or (no container yet) infers a clone URL from
         sibling containers so bootstrap clones it on demand. `source` is None (no
         clone to copy env files from). This is the universal entry point: it works
         with no human clone present.
      2. A `cd` into a human clone — its `origin` URL, with the clone as `source`.

    Fall back to `cwd` (a lagging signal the harness residual-cwd-pin can hold
    stale) when no intent resolves. Returns (None, cwd) when neither yields an
    origin, so main()'s no-origin _err still fires. Fail-open: any unreadable
    intent state → fallback."""
    fallback = (origin_url(cwd), cwd)
    if not session_id:
        return fallback
    try:
        entries = json.loads(intent_path(session_id).read_text())
        if not isinstance(entries, list):
            return fallback
    except Exception:
        return fallback
    base = worktree_base()
    for e in reversed(entries):
        if not (isinstance(e, dict) and e.get('intent') and isinstance(e.get('path'), str)):
            continue
        # ~/wt/<repo> intent: reuse the bare container, else infer a clone URL.
        repo = wt_repo_segment(e['path'], base)
        if repo:
            container = base / repo
            bare_url = origin_url(str(container)) if (container / '.bare').is_dir() else None
            url = bare_url or infer_clone_url(repo, base)
            if url:
                return (url, None)
            # Explicit `cd ~/wt/<repo>` we can't price (no container, no sibling org
            # to infer from). Do NOT fall back to a confident cwd guess — return no
            # URL with the ~/wt path so main() asks the user about this repo.
            return (None, e['path'])
        # Human-clone intent: clone_origin is None for ~/wt worktrees, non-repos,
        # and originless repos — the things that must not become a worktree target.
        url = clone_origin(e['path'])
        if url:
            return (url, e['path'])
    return fallback


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

    # Prefer the most-recent cd-intent over the (possibly pin-stale) cwd. `source`
    # is the clone the env-style files are copied from; `url` derives the container.
    url, source = resolve_target(data.get('session_id'), cwd)
    if not url:
        # If the unresolved target was an explicit `cd ~/wt/<repo>`, name it and
        # ask — rather than guess an org/host that could be wrong.
        unresolved_repo = wt_repo_segment(source, worktree_base()) if source else None
        if unresolved_repo:
            _err(
                f"couldn't determine the clone URL for `{unresolved_repo}`: no bare "
                'container exists yet and no sibling repo to infer the org/host from. '
                'Ask the user for the clone URL or org (or cd into an existing clone) '
                '— do not guess.'
            )
        _err(
            "cannot determine repo: no 'origin' remote in the current directory "
            'and no recent cd-intent into a clone or ~/wt/<repo>. cd into a clone of '
            'the target repo (or ~/wt/<repo>) before calling EnterWorktree.'
        )

    repo = repo_name_from_url(url)

    # Surface a stale cwd transparently: when the intent-derived repo differs from
    # the cwd's repo, the harness pin likely held the cwd stale. Non-fatal — the
    # worktree still lands in the intended (intent-derived) repo. Compare origins,
    # not paths, so a different checkout path of the SAME repo does not warn.
    cwd_url = origin_url(cwd)
    if cwd_url and cwd_url != url:
        print(
            f'ℹ️  target derived from cd-intent ({repo}); cwd looked stale (harness pin): {cwd}',
            file=sys.stderr,
        )

    container = worktree_base() / repo
    worktree_dir = container / name

    # Idempotent re-entry: existing valid worktree at the resolved target → return
    # it. Keyed on the resolved worktree_dir (NOT cwd) so recovery never re-finds a
    # worktree that was wrongly created under a stale-pinned cwd.
    if worktree_dir.is_dir() and is_valid_git_dir(str(worktree_dir)):
        print(str(worktree_dir))
        return

    bootstrap_bare_container(container, url)
    add_worktree(container, worktree_dir, name)
    # source is None for an on-demand ~/wt clone (no human clone to copy env from).
    copy_includes(toplevel(source) if source else None, worktree_dir)

    # Only the worktree path on stdout (Claude Code contract).
    print(str(worktree_dir))


if __name__ == '__main__':
    main()
