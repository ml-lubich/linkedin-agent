from __future__ import annotations

import pytest

import linkedin_agent.scan as scan_mod


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(scan_mod.time, "sleep", lambda s: None)


def test_find_referral_candidates_runs_scroll_loop_and_click_settle(config, monkeypatch):
    """Covers the actual scroll-to-load-more-threads loop and the
    post-click settle sleep, which every other test disables via
    scroll_rounds=0/click_settle_seconds=0 for speed."""
    calls = []
    monkeypatch.setattr(scan_mod, "evaluate", lambda port, script, tab: calls.append(script) or True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "hiring for a role", "unread": True}]}
        return {"lines": ["Jordan Lee: hiring", "View Jordan Lee’s profile"], "url": "https://example.com"}

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(
        config, scroll_rounds=3, sleep_seconds=0.01, click_settle_seconds=0.01
    )
    assert "Jordan Lee" in candidates
    scroll_calls = [c for c in calls if "scrollTop" in c or "scrollTop=" in c]
    assert len(scroll_calls) == 3


def test_find_referral_candidates_keeps_clean_thread(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "hiring for a role", "unread": True}]}
        if args[0] == "read":
            return {
                "lines": ["Jordan Lee: hiring for a role", "View Jordan Lee’s profile"],
                "url": "https://www.linkedin.com/messaging/thread/abc/",
            }
        raise AssertionError(f"unexpected li call {args}")

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(
        config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0
    )
    assert "Jordan Lee" in candidates
    assert candidates["Jordan Lee"].unread is True
    assert candidates["Jordan Lee"].url.endswith("abc/")


def test_find_referral_candidates_skips_own_last_message(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "hiring for a role", "unread": False}]}
        return {
            "lines": ["Jordan Lee: hi", f"View {config.self_name}’s profile"],
            "url": "https://example.com/thread",
        }

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0)
    assert candidates == {}


def test_find_referral_candidates_skips_you_preview(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "You: sounds good", "unread": False}]}
        raise AssertionError("read should not be called for a You: preview")

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0)
    assert candidates == {}


def test_find_referral_candidates_skips_wrong_thread_click(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "hiring", "unread": False}]}
        return {"lines": ["completely unrelated content"], "url": "https://example.com"}

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0)
    assert candidates == {}


def test_find_referral_candidates_skips_excluded(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Blocked Person", "preview": "hi", "unread": False}]}
        return {
            "lines": ["Blocked Person: hiring for a role", "View Blocked Person’s profile"],
            "url": "https://example.com",
        }

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0)
    assert candidates == {}


def test_find_referral_candidates_skips_already_referred(config, monkeypatch):
    monkeypatch.setattr(scan_mod, "evaluate", lambda *a, **k: True)

    def fake_li(*args, port=None, **kwargs):
        if args[0] == "threads":
            return {"threads": [{"name": "Jordan Lee", "preview": "hiring", "unread": False}]}
        return {
            "lines": [
                "Jordan Lee: hiring for a role",
                f"mentioned {config.referral.email} already",
                "View Jordan Lee’s profile",
            ],
            "url": "https://example.com",
        }

    monkeypatch.setattr(scan_mod, "li", fake_li)
    candidates = scan_mod.find_referral_candidates(config, scroll_rounds=0, sleep_seconds=0, click_settle_seconds=0)
    assert candidates == {}
