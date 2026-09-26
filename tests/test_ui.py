from __future__ import annotations

import pytest

from linkedin_agent import ui


def test_is_no_color_respects_env(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ui.is_no_color() is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.is_no_color() is True


def test_is_tty_false_for_non_tty_stream():
    class Fake:
        def isatty(self):
            return False

    assert ui.is_tty(Fake()) is False


def test_is_tty_true_for_tty_stream():
    class Fake:
        def isatty(self):
            return True

    assert ui.is_tty(Fake()) is True


def test_is_tty_handles_missing_isatty():
    class Weird:
        pass

    assert ui.is_tty(Weird()) is False


def test_is_plain_true_when_no_color_set(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.is_plain() is True


def test_is_plain_true_when_not_a_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: False)
    assert ui.is_plain() is True


def test_is_plain_false_when_color_and_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    assert ui.is_plain() is False


@pytest.mark.parametrize(
    "word",
    ["A", "Z", "LINKEDIN", "linkedin-agent", "IMSG", "WA", "INOTES", "IMAIL", "0129", "-.", "  ", ""],
)
def test_render_ascii_always_returns_five_equal_length_rows(word):
    rows = ui.render_ascii(word)
    assert len(rows) == 5
    widths = {len(row) for row in rows}
    assert len(widths) <= 1  # every row is the same width


def test_render_ascii_unknown_character_is_blank_not_a_crash():
    rows = ui.render_ascii("A!B")
    assert len(rows) == 5
    for row in rows:
        assert len(row) > 0


@pytest.mark.parametrize("no_color,tty", [(True, True), (True, False), (False, False)])
def test_banner_plain_mode_prints_single_line(monkeypatch, capsys, no_color, tty):
    monkeypatch.setattr(ui, "is_no_color", lambda: no_color)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: tty)
    ui.banner("Name", "1.2.3", "tagline here")
    out = capsys.readouterr().out
    assert "Name v1.2.3" in out
    assert "tagline here" in out


def test_banner_color_mode_prints_ascii_art(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.banner("AB", "0.1.0")
    out = capsys.readouterr().out
    assert "█" in out  # block character from the dot-matrix font
    assert "v0.1.0" in out


def test_banner_color_mode_with_version_and_tagline_combines_meta_line(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.banner("AB", "2.0.0", "a tagline")
    out = capsys.readouterr().out
    assert "v2.0.0" in out
    assert "a tagline" in out


def test_banner_color_mode_tagline_only_no_version(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.banner("AB", "", "just a tagline")
    out = capsys.readouterr().out
    assert "just a tagline" in out


def test_banner_without_version_or_tagline(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: False)
    ui.banner("Name")
    out = capsys.readouterr().out
    assert out.strip() == "Name"


def test_example_panel_plain(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    ui.example_panel([("cmd one", "does one"), ("cmd two", "")])
    out = capsys.readouterr().out
    assert "cmd one" in out
    assert "does one" in out
    assert "cmd two" in out


def test_example_panel_rich(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.example_panel([("cmd", "desc")], title="Custom Title")
    out = capsys.readouterr().out
    assert "Custom Title" in out
    assert "cmd" in out


def test_example_panel_rich_multiple_items_adds_separators(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.example_panel([("cmd one", "first"), ("cmd two", ""), ("cmd three", "third")])
    out = capsys.readouterr().out
    assert "cmd one" in out
    assert "cmd two" in out
    assert "cmd three" in out


@pytest.mark.parametrize("passed,plain", [(True, True), (False, True), (True, False), (False, False)])
def test_mark_and_print_check(monkeypatch, capsys, passed, plain):
    monkeypatch.setattr(ui, "is_no_color", lambda: plain)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: not plain)
    ui.print_check("some check", passed, "detail text")
    out = capsys.readouterr().out
    assert "some check" in out
    assert "detail text" in out


def test_print_ok_and_print_fail(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    ui.print_ok("all good")
    ui.print_fail("uh oh")
    out = capsys.readouterr().out
    assert "OK" in out
    assert "FAIL" in out


def test_draft_panel_plain(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    ui.draft_panel("hello world")
    out = capsys.readouterr().out
    assert "NOT SENT" in out
    assert "hello world" in out


def test_draft_panel_rich(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.draft_panel("hello world", title="CUSTOM")
    out = capsys.readouterr().out
    assert "CUSTOM" in out
    assert "hello world" in out


def test_render_table_plain(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    ui.render_table("My Table", ["A", "B"], [["1", "2"], ["3", "4"]])
    out = capsys.readouterr().out
    assert "My Table" in out
    assert "1" in out and "4" in out


def test_render_table_rich(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    ui.render_table("My Table", ["A", "B"], [["x", "y"]])
    out = capsys.readouterr().out
    assert "My Table" in out
    assert "x" in out


def test_render_table_empty_rows(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    ui.render_table("Empty", ["A"], [])
    out = capsys.readouterr().out
    assert "Empty" in out


def test_spinner_plain_yields(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: True)
    with ui.spinner("working"):
        did_work = True
    assert did_work
    err = capsys.readouterr().err
    assert "working" in err


def test_spinner_rich_yields(monkeypatch, capsys):
    monkeypatch.setattr(ui, "is_no_color", lambda: False)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: True)
    with ui.spinner("working"):
        did_work = True
    assert did_work


def test_make_console_force_terminal_none_when_not_plain(monkeypatch):
    monkeypatch.setattr(ui, "is_plain", lambda: False)
    console = ui.make_console()
    assert console is not None


def test_ok_helper_returns_message():
    assert ui.ok("hi") == "hi"


@pytest.mark.parametrize("plain", [True, False])
def test_mark_direct_both_modes(monkeypatch, plain):
    monkeypatch.setattr(ui, "is_no_color", lambda: plain)
    monkeypatch.setattr(ui, "is_tty", lambda stream=None: not plain)
    assert ui.mark(True) == ("OK " if plain else "[green]✓[/]")
    assert ui.mark(False) == ("FAIL" if plain else "[red]✗[/]")
