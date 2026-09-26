from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import linkedin_agent.cli as cli_mod
from linkedin_agent.governor import RateLimited
from linkedin_agent.messaging import SendNotConfirmedError
from linkedin_agent.referral import ReferralResult
from linkedin_agent.scan import Candidate

runner = CliRunner()


@pytest.fixture(autouse=True)
def _config(config, monkeypatch):
    monkeypatch.setattr(cli_mod, "load_config", lambda: config)
    cli_mod.STATE["port"] = None
    return config


# ---------------------------------------------------------------- doctor ----


def test_doctor_ok(monkeypatch):
    monkeypatch.setattr(cli_mod.doctor_mod, "check", lambda cfg: {"ok": True, "checks": []})
    result = runner.invoke(cli_mod.app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_not_ok(monkeypatch):
    monkeypatch.setattr(cli_mod.doctor_mod, "check", lambda cfg: {"ok": False, "checks": []})
    result = runner.invoke(cli_mod.app, ["doctor"])
    assert result.exit_code == 1


def test_doctor_json(monkeypatch):
    monkeypatch.setattr(cli_mod.doctor_mod, "check", lambda cfg: {"ok": True, "checks": [{"name": "x", "ok": True}]})
    result = runner.invoke(cli_mod.app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_doctor_shows_each_check_line(monkeypatch):
    monkeypatch.setattr(
        cli_mod.doctor_mod,
        "check",
        lambda cfg: {
            "ok": False,
            "checks": [
                {"name": "a", "ok": True, "detail": "fine"},
                {"name": "b", "ok": False, "detail": "broken"},
            ],
        },
    )
    result = runner.invoke(cli_mod.app, ["doctor"])
    assert "a" in result.output
    assert "b" in result.output
    assert result.exit_code == 1


# ------------------------------------------------------------------ scan ----


def test_scan_table(monkeypatch):
    monkeypatch.setattr(
        cli_mod.scan_mod,
        "find_referral_candidates",
        lambda cfg, port=None: {"Jordan": Candidate(name="Jordan", url="u", unread=True, text="t")},
    )
    result = runner.invoke(cli_mod.app, ["scan"])
    assert result.exit_code == 0
    assert "Jordan" in result.output


def test_scan_json(monkeypatch):
    monkeypatch.setattr(
        cli_mod.scan_mod,
        "find_referral_candidates",
        lambda cfg, port=None: {"Jordan": Candidate(name="Jordan", url="u", unread=False, text="t")},
    )
    result = runner.invoke(cli_mod.app, ["scan", "--json"])
    payload = json.loads(result.stdout)
    assert payload["Jordan"]["unread"] is False


def test_scan_empty(monkeypatch):
    monkeypatch.setattr(cli_mod.scan_mod, "find_referral_candidates", lambda cfg, port=None: {})
    result = runner.invoke(cli_mod.app, ["scan", "--json"])
    assert json.loads(result.stdout) == {}


# -------------------------------------------------------------- classify ----


@pytest.mark.parametrize(
    "text,expect_hiring",
    [
        ("we are hiring for a role", True),
        ("InMail: exciting opportunity", True),
        ("want to grab coffee?", False),
        ("", False),
        ("\U0001f680\U0001f680\U0001f680 hiring emoji spam \U0001f680\U0001f680\U0001f680", True),
    ],
)
def test_classify_hiring_flag(text, expect_hiring):
    result = runner.invoke(cli_mod.app, ["classify", text, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["hiring"] is expect_hiring


def test_classify_json():
    result = runner.invoke(cli_mod.app, ["classify", "we are hiring", "--json", "--name", "Jordan"])
    payload = json.loads(result.stdout)
    assert payload["hiring"] is True


def test_classify_plain_output():
    result = runner.invoke(cli_mod.app, ["classify", "we are hiring"])
    assert "hiring: True" in result.output


def test_classify_excluded(config):
    result = runner.invoke(cli_mod.app, ["classify", "hi there", "--name", "Blocked Person", "--json"])
    payload = json.loads(result.stdout)
    assert payload["excluded"] is True


# --------------------------------------------------------- draft-referral ----


def test_draft_referral_disabled(disabled_config, monkeypatch):
    monkeypatch.setattr(cli_mod, "load_config", lambda: disabled_config)
    result = runner.invoke(cli_mod.app, ["draft-referral", "Jordan", "hiring for a role"])
    assert result.exit_code == 1


def test_draft_referral_success_json():
    result = runner.invoke(cli_mod.app, ["draft-referral", "Jordan Lee", "Exciting AI role at Acme", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["problems"] == []


def test_draft_referral_success_panel():
    result = runner.invoke(cli_mod.app, ["draft-referral", "Jordan Lee", "Exciting AI role at Acme"])
    assert result.exit_code == 0
    assert "jordan" in result.output.lower()


def test_draft_referral_plain_mode_shows_lint_problems(monkeypatch):
    # Unit-testing the CLI's plain-mode wiring for "lint found problems" --
    # the lint logic itself (assert_human_copy) has its own tests, this just
    # checks the CLI prints the problems line and exits 2 when it's non-empty.
    monkeypatch.setattr(cli_mod.copywriter_mod, "assert_human_copy", lambda draft, cfg: ["ai-tell:delve"])
    result = runner.invoke(cli_mod.app, ["draft-referral", "Sam", "some role"])
    assert result.exit_code == 2
    assert "lint problems" in result.output


def test_draft_referral_reengage_and_stale_days():
    result = runner.invoke(
        cli_mod.app,
        ["draft-referral", "Sam", "checking in", "--reengage", "--stale-days", "10", "--json"],
    )
    payload = json.loads(result.stdout)
    assert "long time no see" in payload["draft"]


# ---------------------------------------------------------- send-referral ----


def test_send_referral_not_confirmed(monkeypatch):
    def raise_confirm(**kwargs):
        raise SendNotConfirmedError("nope")

    monkeypatch.setattr(cli_mod.referral_mod, "send_referral_for_candidate", raise_confirm)
    result = runner.invoke(cli_mod.app, ["send-referral", "Jordan", "https://example.com"])
    assert result.exit_code == 3


def test_send_referral_skipped_json(monkeypatch):
    monkeypatch.setattr(
        cli_mod.referral_mod,
        "send_referral_for_candidate",
        lambda **kwargs: ReferralResult(name="Jordan", skipped="already referred"),
    )
    result = runner.invoke(cli_mod.app, ["send-referral", "Jordan", "https://example.com", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["skipped"] == "already referred"


def test_send_referral_skipped_plain(monkeypatch):
    monkeypatch.setattr(
        cli_mod.referral_mod,
        "send_referral_for_candidate",
        lambda **kwargs: ReferralResult(name="Jordan", skipped="already referred"),
    )
    result = runner.invoke(cli_mod.app, ["send-referral", "Jordan", "https://example.com"])
    assert result.exit_code == 2
    assert "already referred" in result.output


def test_send_referral_success(monkeypatch):
    monkeypatch.setattr(
        cli_mod.referral_mod,
        "send_referral_for_candidate",
        lambda **kwargs: ReferralResult(name="Jordan", draft="hi", proof={"sent": True}),
    )
    result = runner.invoke(cli_mod.app, ["send-referral", "Jordan", "https://example.com", "--confirm"])
    assert result.exit_code == 0


def test_send_referral_success_json(monkeypatch):
    monkeypatch.setattr(
        cli_mod.referral_mod,
        "send_referral_for_candidate",
        lambda **kwargs: ReferralResult(name="Jordan", draft="hi", proof={"sent": True}),
    )
    result = runner.invoke(cli_mod.app, ["send-referral", "Jordan", "https://example.com", "--confirm", "--json"])
    assert json.loads(result.stdout)["proof"]["sent"] is True


# ---------------------------------------------------------- message read ----


def test_message_read_without_url(monkeypatch):
    monkeypatch.setattr(cli_mod, "read_thread_fn", lambda port, limit: {"bodies": [], "url": "u"})
    result = runner.invoke(cli_mod.app, ["message", "read"])
    assert result.exit_code == 0


def test_message_read_with_url(monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_mod, "open_thread_fn", lambda url, port: calls.setdefault("url", url))
    monkeypatch.setattr(cli_mod, "read_thread_fn", lambda port, limit: {"bodies": ["hi"], "url": "u"})
    result = runner.invoke(cli_mod.app, ["message", "read", "--url", "https://example.com"])
    assert result.exit_code == 0
    assert calls["url"] == "https://example.com"


def test_message_read_json(monkeypatch):
    monkeypatch.setattr(cli_mod, "read_thread_fn", lambda port, limit: {"bodies": ["a", "b"], "url": "u"})
    result = runner.invoke(cli_mod.app, ["message", "read", "--json"])
    payload = json.loads(result.stdout)
    assert payload["bodies"] == ["a", "b"]


def test_message_read_limit_passed_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli_mod, "read_thread_fn", lambda port, limit: captured.setdefault("limit", limit) or {"bodies": []}
    )
    runner.invoke(cli_mod.app, ["message", "read", "--limit", "7"])
    assert captured["limit"] == 7


# ---------------------------------------------------------- message send ----


def test_message_send_not_confirmed(monkeypatch):
    def raise_confirm(**kwargs):
        raise SendNotConfirmedError("nope")

    monkeypatch.setattr(cli_mod, "send_message_fn", raise_confirm)
    result = runner.invoke(cli_mod.app, ["message", "send", "hello"])
    assert result.exit_code == 3


def test_message_send_success(monkeypatch):
    monkeypatch.setattr(cli_mod, "send_message_fn", lambda **kwargs: {"sent": True})
    result = runner.invoke(cli_mod.app, ["message", "send", "hello", "--confirm"])
    assert result.exit_code == 0


def test_message_send_json(monkeypatch):
    monkeypatch.setattr(cli_mod, "send_message_fn", lambda **kwargs: {"sent": True})
    result = runner.invoke(cli_mod.app, ["message", "send", "hello", "--confirm", "--json"])
    assert json.loads(result.stdout)["sent"] is True


def test_message_send_rate_limited(monkeypatch):
    def raise_rate_limited(**kwargs):
        raise RateLimited("message budget exhausted")

    monkeypatch.setattr(cli_mod, "send_message_fn", raise_rate_limited)
    result = runner.invoke(cli_mod.app, ["message", "send", "hello", "--confirm", "--target", "alice"])
    assert result.exit_code == 4


def test_message_send_passes_target_and_attach(monkeypatch):
    captured = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return {"sent": True}

    monkeypatch.setattr(cli_mod, "send_message_fn", fake_send)
    runner.invoke(
        cli_mod.app,
        ["message", "send", "hello", "--confirm", "--target", "alice", "--attach", "/tmp/x.pdf", "--attach-name", "r.pdf"],
    )
    assert captured["target"] == "alice"
    assert captured["attachment_path"] == "/tmp/x.pdf"
    assert captured["attachment_name_hint"] == "r.pdf"


# -------------------------------------------------------------- post draft --


def test_post_draft_clean():
    result = runner.invoke(cli_mod.app, ["post", "draft", "Shipped a small thing this week."])
    assert result.exit_code == 0


def test_post_draft_dirty():
    result = runner.invoke(cli_mod.app, ["post", "draft", "Excited to announce our leveraging platform!"])
    assert result.exit_code == 2


def test_post_draft_json():
    result = runner.invoke(cli_mod.app, ["post", "draft", "clean text", "--json"])
    payload = json.loads(result.stdout)
    assert payload["problems"] == []


# ------------------------------------------------------------ post publish --


def test_post_publish_not_confirmed(monkeypatch):
    def raise_confirm(**kwargs):
        raise SendNotConfirmedError("nope")

    monkeypatch.setattr(cli_mod.post_mod, "publish_post", raise_confirm)
    result = runner.invoke(cli_mod.app, ["post", "publish", "hello"])
    assert result.exit_code == 3


def test_post_publish_success(monkeypatch):
    monkeypatch.setattr(cli_mod.post_mod, "publish_post", lambda **kwargs: {"clicked_post": True})
    result = runner.invoke(cli_mod.app, ["post", "publish", "hello", "--confirm"])
    assert result.exit_code == 0


def test_post_publish_json(monkeypatch):
    monkeypatch.setattr(cli_mod.post_mod, "publish_post", lambda **kwargs: {"clicked_post": True})
    result = runner.invoke(cli_mod.app, ["post", "publish", "hello", "--confirm", "--json"])
    assert json.loads(result.stdout)["clicked_post"] is True


def test_post_publish_rate_limited(monkeypatch):
    def raise_rate_limited(**kwargs):
        raise RateLimited("post budget exhausted")

    monkeypatch.setattr(cli_mod.post_mod, "publish_post", raise_rate_limited)
    result = runner.invoke(cli_mod.app, ["post", "publish", "hello", "--confirm"])
    assert result.exit_code == 4


# --------------------------------------------------------------- wiring ----


def test_port_override_reaches_state(monkeypatch):
    monkeypatch.setattr(cli_mod.doctor_mod, "check", lambda cfg: {"ok": True, "checks": []})
    runner.invoke(cli_mod.app, ["--port", "9333", "doctor"])
    assert cli_mod.STATE["port"] == 9333


def test_app_invoked_directly_with_no_subcommand_shows_banner():
    # Exercises main_callback's own `ctx.invoked_subcommand is None` branch
    # directly through Click, bypassing the `main()` wrapper's early return.
    result = runner.invoke(cli_mod.app, [])
    assert "LINKEDIN-AGENT" in result.output


def test_no_subcommand_shows_banner_and_exits_zero(capsys):
    code = cli_mod.main([])
    out = capsys.readouterr().out
    assert "LINKEDIN-AGENT" in out or "LINKEDIN" in out
    assert code == 0


def test_help_flag_shows_banner_and_usage(capsys):
    code = cli_mod.main(["--help"])
    out = capsys.readouterr().out
    assert "Usage" in out
    assert code == 0


def test_unknown_command_nonzero_exit():
    result = runner.invoke(cli_mod.app, ["not-a-real-command"])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["classify"],  # missing required TEXT
        ["draft-referral", "OnlyName"],  # missing required TEXT
        ["send-referral", "OnlyName"],  # missing required URL
        ["message", "send"],  # missing required TEXT
        ["post", "draft"],  # missing required TEXT
        ["post", "publish"],  # missing required TEXT
    ],
)
def test_missing_required_arg_is_nonzero_exit(args):
    result = runner.invoke(cli_mod.app, args)
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["doctor", "--not-a-flag"],
        ["scan", "--bogus"],
        ["message", "send", "hi", "--nope"],
    ],
)
def test_unknown_flag_is_nonzero_exit(args):
    result = runner.invoke(cli_mod.app, args)
    assert result.exit_code != 0


def test_to_jsonable_handles_dataclass_list_and_scalar():
    result = ReferralResult(name="x", proof={"a": 1})
    payload = cli_mod._to_jsonable([result, {"nested": result}, "plain", 3])
    assert payload[0]["name"] == "x"
    assert payload[1]["nested"]["proof"] == {"a": 1}
    assert payload[2] == "plain"
    assert payload[3] == 3


def test_chrome_error_prints_clean_failure_not_traceback(monkeypatch, capsys):
    from own_chrome.cdp import ChromeError
    from linkedin_agent import cli

    def boom(*_a, **_k):
        raise ChromeError("no compose box on page")

    monkeypatch.setattr(cli, "app", boom)
    assert cli.main(["scan"]) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "no compose box on page" in text
    assert "Traceback" not in text
