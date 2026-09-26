from __future__ import annotations

import socket as _socket_mod

import pytest

from linkedin_agent.config import Config, PitchRule, ReferralConfig


@pytest.fixture(autouse=True)
def _block_real_sockets(monkeypatch):
    """Safety net for the "mock only CDP/network" rule: any test that
    forgets to mock the CDP boundary and tries to open a real socket
    (own_chrome.cdp, linkedin_agent.cdp_session) fails loudly here instead of
    silently touching a real Chrome. Tests that specifically exercise the
    socket/handshake layer (test_cdp_session.py) monkeypatch
    `socket.create_connection` themselves, which overrides this for their
    own scope."""

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "test opened a real socket.create_connection() -- mock the CDP boundary "
            "(own_chrome.cdp.evaluate/navigate/pick_page, or cdp_session.set_file_input) instead"
        )

    monkeypatch.setattr(_socket_mod, "create_connection", _blocked)


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        cdp_port=9222,
        self_name="Agent Self",
        governor_db_path=str(tmp_path / "governor.db"),
        referral=ReferralConfig(
            enabled=True,
            name="Referee Person",
            email="referee@example.com",
            linkedin_url="https://www.linkedin.com/in/referee-example/",
            resume_path="/tmp/referee_resume.pdf",
            attachment_name="resume.pdf",
            pitch=[
                PitchRule(keywords=["data", "analytics"], text="built data platforms that shipped"),
                PitchRule(keywords=["default"], text="is a strong generalist engineer"),
            ],
        ),
        reserved_for_self=["Reserved Co"],
        never_contact=["Blocked Person"],
        share_contact="decline",
    )


@pytest.fixture
def disabled_config(tmp_path) -> Config:
    return Config(governor_db_path=str(tmp_path / "governor-disabled.db"))


# Reused across many parametrized edge-case tables: empty, whitespace-only,
# unicode, emoji (incl. a ZWJ family sequence), very long, injection-shaped,
# control/newline characters, and a null byte. The point of each case is
# "must not crash and must return a sane type", not a specific value.
EDGE_STRINGS: list[str] = [
    "",
    " ",
    "   \t\n  ",
    "a",
    "héllo wörld café",
    "\U0001f680\U0001f525\U0001f4af",
    "\U0001f468‍\U0001f469‍\U0001f467‍\U0001f466",
    "x" * 5000,
    "'; DROP TABLE actions; --",
    "<script>alert(1)</script>",
    "line1\nline2\r\nline3",
    "\x00null\x00byte",
    "مرحبا",  # Arabic "hello" (RTL)
    "Hello 世界 \U0001f30d",  # mixed scripts + emoji
    "control\x07bell\x1bchars",
    "-----BEGIN PRIVATE KEY-----",
    "{{7*7}}",  # template-injection-shaped
    "a" * 65600,  # forces the 2-byte-length WS frame branch if ever framed
]
