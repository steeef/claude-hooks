"""Tests for shell alias cache in command_utils."""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'plugins' / 'git-hooks' / 'hooks'))

import command_utils  # noqa: E402


def _reset(monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path))
    monkeypatch.setenv('SHELL', '/bin/zsh')
    monkeypatch.setattr(command_utils, '_alias_cache', None)
    return tmp_path / 'claude-hooks'


def test_timeout_writes_fail_marker_and_skips_retry(monkeypatch, tmp_path):
    cache_dir = _reset(monkeypatch, tmp_path)
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired(cmd='zsh', timeout=5)

    monkeypatch.setattr(command_utils.subprocess, 'run', fake_run)

    assert command_utils._load_alias_cache() == {}
    assert (cache_dir / 'aliases-zsh.json.fail').exists()
    assert len(calls) == 1

    monkeypatch.setattr(command_utils, '_alias_cache', None)
    assert command_utils._load_alias_cache() == {}
    assert len(calls) == 1


def test_stale_fail_marker_retries(monkeypatch, tmp_path):
    cache_dir = _reset(monkeypatch, tmp_path)
    cache_dir.mkdir()
    marker = cache_dir / 'aliases-zsh.json.fail'
    marker.touch()
    old = marker.stat().st_mtime - command_utils.ALIAS_FAIL_TTL - 1
    os.utime(marker, (old, old))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="gco='git checkout'\n")

    monkeypatch.setattr(command_utils.subprocess, 'run', fake_run)

    assert command_utils._load_alias_cache() == {'gco': 'git checkout'}
    assert (cache_dir / 'aliases-zsh.json').exists()
