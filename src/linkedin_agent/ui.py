"""Shared Rich CLI look: gradient banner, ok/fail marks, tables, panels.

No project-specific logic lives here on purpose -- this file is meant to be
copied as-is into other CLIs (imsg, wa, inotes, imail, ...) for a consistent
look. Dependency: rich only. Honours NO_COLOR and non-TTY output.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterable, Iterator, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# LinkedIn blue -> cyan.
GRADIENT = ["#0A66C2", "#1878C6", "#2B96D1", "#4CC4E4", "#67E8F9"]

# Minimal 5x5 dot-matrix font, uppercase + digits + '-' '.' ' '. Good enough
# for a decorative banner, not a general-purpose font renderer.
_FONT: dict[str, tuple[str, str, str, str, str]] = {
    "A": ("01110", "10001", "11111", "10001", "10001"),
    "B": ("11110", "10001", "11110", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "11110", "10000", "11111"),
    "F": ("11111", "10000", "11110", "10000", "10000"),
    "G": ("01111", "10000", "10111", "10001", "01111"),
    "H": ("10001", "10001", "11111", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00001", "00001", "10001", "01110"),
    "K": ("10001", "10010", "11100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001"),
    "O": ("01110", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "11110", "10000", "10000"),
    "Q": ("01110", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "11110", "10010", "10001"),
    "S": ("01111", "10000", "01110", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10101", "11011", "10001"),
    "X": ("10001", "01010", "00100", "01010", "10001"),
    "Y": ("10001", "01010", "00100", "00100", "00100"),
    "Z": ("11111", "00010", "00100", "01000", "11111"),
    "0": ("01110", "10011", "10101", "11001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00010", "00100", "11111"),
    "3": ("11110", "00001", "00110", "00001", "11110"),
    "4": ("10010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "11110"),
    "6": ("01110", "10000", "11110", "10001", "01110"),
    "7": ("11111", "00010", "00100", "00100", "00100"),
    "8": ("01110", "10001", "01110", "10001", "01110"),
    "9": ("01110", "10001", "01111", "00001", "01110"),
    "-": ("00000", "00000", "11111", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00100"),
    " ": ("00000", "00000", "00000", "00000", "00000"),
}
_BLOCK = "█"


def is_no_color() -> bool:
    return bool(os.environ.get("NO_COLOR"))


def is_tty(stream=None) -> bool:
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def is_plain() -> bool:
    """True when color/fancy output should be suppressed: NO_COLOR is set, or
    stdout isn't a terminal (piped/redirected/captured)."""
    return is_no_color() or not is_tty()


def make_console(**kwargs) -> Console:
    return Console(no_color=is_no_color(), force_terminal=False if is_plain() else None, **kwargs)


console = make_console()
# Transient progress/status text (spinners) goes to stderr so stdout stays
# clean for actual command output, including --json. stderr=True (not
# file=sys.stderr) so this keeps tracking sys.stderr if it's ever swapped
# (e.g. pytest's capsys), instead of binding to today's object forever.
err_console = make_console(stderr=True)


def _gradient_text(line: str, colors: Sequence[str]) -> Text:
    text = Text()
    width = max(len(line), 1)
    for i, ch in enumerate(line):
        color = colors[min(int(i / width * len(colors)), len(colors) - 1)]
        text.append(ch, style=color)
    return text


def render_ascii(word: str) -> list[str]:
    """Render `word` (any case) as 5 rows of block-character ascii art. Unknown
    characters render as a blank glyph rather than raising."""
    glyphs = [_FONT.get(ch.upper(), _FONT[" "]) for ch in word]
    rows = []
    for row_index in range(5):
        pieces = []
        for glyph in glyphs:
            bits = glyph[row_index]
            pieces.append("".join(_BLOCK if b == "1" else " " for b in bits))
        rows.append(" ".join(pieces))
    return rows


def banner(name: str, version: str = "", tagline: str = "") -> None:
    """Print a gradient ascii-art banner, or a single plain line when color
    output is suppressed (NO_COLOR / non-TTY)."""
    if is_plain():
        line = name if not version else f"{name} v{version}"
        console.print(line)
        if tagline:
            console.print(tagline)
        return
    for row in render_ascii(name):
        console.print(_gradient_text(row, GRADIENT))
    meta = f"v{version}" if version else ""
    if tagline:
        meta = f"{meta}   {tagline}" if meta else tagline
    if meta:
        console.print(meta, style="dim")


def example_panel(examples: Iterable[tuple[str, str]], title: str = "Try:") -> None:
    """A short panel of `(command, description)` pairs, or a plain list when
    color output is suppressed."""
    if is_plain():
        console.print(f"{title}")
        for cmd, desc in examples:
            console.print(f"  {cmd}    # {desc}")
        return
    body = Text()
    for i, (cmd, desc) in enumerate(examples):
        if i:
            body.append("\n")
        body.append("$ ", style="dim")
        body.append(cmd, style="bold cyan")
        if desc:
            body.append(f"   # {desc}", style="dim")
    console.print(Panel(body, title=title, border_style="blue", expand=False))


def ok(msg: str) -> str:
    return msg if is_plain() else msg


def mark(passed: bool) -> str:
    if is_plain():
        return "OK " if passed else "FAIL"
    return "[green]✓[/]" if passed else "[red]✗[/]"


def print_check(name: str, passed: bool, detail: str = "") -> None:
    suffix = f" -- {detail}" if detail else ""
    if is_plain():
        console.print(f"[{'OK' if passed else 'FAIL'}] {name}{suffix}")
        return
    console.print(f"{mark(passed)} {name}{suffix}")


def print_ok(msg: str) -> None:
    print_check(msg, True)


def print_fail(msg: str) -> None:
    print_check(msg, False)


def draft_panel(text: str, title: str = "DRAFT — NOT SENT") -> None:
    if is_plain():
        console.print(f"[{title}]")
        console.print(text)
        return
    console.print(Panel(Text(text), title=title, border_style="yellow", expand=False))


def render_table(title: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    if is_plain():
        console.print(title)
        console.print(" | ".join(columns))
        for row in rows:
            console.print(" | ".join(str(cell) for cell in row))
        return
    table = Table(title=title, border_style="blue")
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    console.print(table)


@contextmanager
def spinner(text: str) -> Iterator[None]:
    if is_plain():
        err_console.print(f"{text} ...")
        yield
        return
    with err_console.status(text, spinner="dots"):
        yield
