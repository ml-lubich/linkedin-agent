"""Thin subprocess wrapper around own-chrome's `li` and `own-chrome` CLIs.

We shell out to the installed commands rather than importing own_chrome's CLI
modules directly, because `li`/`own-chrome` are the stable, documented
surface -- their internal argparse wiring is not.
"""

from __future__ import annotations

import json
import shutil
import subprocess


class LiCliError(RuntimeError):
    pass


def li(*args: str, port: int | None = None, timeout: float = 15.0) -> dict:
    """Run `li <args> --json` and parse stdout. Raises LiCliError on failure."""
    if shutil.which("li") is None:
        raise LiCliError("the `li` command is not installed (pip/uv install own-chrome)")
    cmd = ["li", *args, "--json"]
    if port is not None:
        cmd += ["--port", str(port)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode not in (0, 2):
        raise LiCliError(f"li {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    text = proc.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LiCliError(f"li did not return JSON: {text[:200]!r}") from exc


def own_chrome_status(port: int | None = None, needle: str = "", timeout: float = 15.0) -> dict:
    if shutil.which("own-chrome") is None:
        raise LiCliError("the `own-chrome` command is not installed (pip/uv install own-chrome)")
    cmd = ["own-chrome", "status", "--json"]
    if port is not None:
        cmd += ["--port", str(port)]
    if needle:
        cmd += ["--filter", needle]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise LiCliError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout.strip() or "{}")
