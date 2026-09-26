from __future__ import annotations

import subprocess

import pytest

from linkedin_agent.li_cli import LiCliError, li, own_chrome_status


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_li_missing_binary(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(LiCliError):
        li("threads")


def test_li_success(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/li")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: FakeCompletedProcess(0, '{"threads": []}', "")
    )
    result = li("threads", port=9222)
    assert result == {"threads": []}


def test_li_empty_stdout(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/li")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompletedProcess(2, "", ""))
    assert li("unread") == {}


def test_li_bad_json_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/li")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompletedProcess(0, "not json", ""))
    with pytest.raises(LiCliError):
        li("threads")


def test_li_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/li")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompletedProcess(1, "", "boom"))
    with pytest.raises(LiCliError, match="boom"):
        li("threads")


def test_own_chrome_status_missing_binary(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(LiCliError):
        own_chrome_status()


def test_own_chrome_status_success(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/own-chrome")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: FakeCompletedProcess(0, '{"pid": 1}', "")
    )
    assert own_chrome_status(port=9222, needle="linkedin") == {"pid": 1}


def test_own_chrome_status_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/own-chrome")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeCompletedProcess(1, "", "nope"))
    with pytest.raises(LiCliError, match="nope"):
        own_chrome_status()
