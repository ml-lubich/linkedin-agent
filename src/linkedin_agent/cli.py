"""linkedin-agent command line (Typer + Rich)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Optional

import typer
from own_chrome.cdp import ChromeError

from linkedin_agent import __version__
from linkedin_agent import classify as classify_mod
from linkedin_agent import copywriter as copywriter_mod
from linkedin_agent import doctor as doctor_mod
from linkedin_agent import post as post_mod
from linkedin_agent import referral as referral_mod
from linkedin_agent import scan as scan_mod
from linkedin_agent import ui
from linkedin_agent.config import load_config
from linkedin_agent.governor import RateLimited
from linkedin_agent.messaging import SendNotConfirmedError
from linkedin_agent.messaging import open_thread as open_thread_fn
from linkedin_agent.messaging import read_thread as read_thread_fn
from linkedin_agent.messaging import send_message as send_message_fn

NAME = "LINKEDIN-AGENT"
TAGLINE = "drive your own logged-in Chrome, over CDP"
EXAMPLES = [
    ("linkedin-agent doctor", "check own-chrome/li, Chrome CDP, login state"),
    ("linkedin-agent scan", "find threads that still need a reply"),
    ("linkedin-agent message read --limit 20", "read the open thread"),
    ('linkedin-agent post draft "..."', "lint a post before publishing"),
    ("linkedin-agent send-referral NAME URL --confirm", "send a referral, once confirmed"),
]

STATE: dict = {"port": None}

app = typer.Typer(
    name="linkedin-agent",
    help="Drive LinkedIn in your own logged-in Chrome.",
    add_completion=False,
)
message_app = typer.Typer(help="Read or send a message in the open thread.", no_args_is_help=True)
post_app = typer.Typer(help="Draft or publish a feed post.", no_args_is_help=True)
app.add_typer(message_app, name="message")
app.add_typer(post_app, name="post")


def _to_jsonable(payload: object) -> object:
    if is_dataclass(payload) and not isinstance(payload, type):
        return asdict(payload)
    if isinstance(payload, dict):
        return {k: _to_jsonable(v) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_to_jsonable(v) for v in payload]
    return payload


def _emit_json(payload: object) -> None:
    json.dump(_to_jsonable(payload), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _fail_not_confirmed(exc: SendNotConfirmedError) -> None:
    ui.console.print(str(exc), style="red")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    port: Optional[int] = typer.Option(None, "--port", help="CDP port override"),
) -> None:
    STATE["port"] = port
    if ctx.invoked_subcommand is None:
        ui.banner(NAME, __version__, TAGLINE)
        ui.example_panel(EXAMPLES)
        raise typer.Exit(0)


@app.command()
def doctor(json_out: bool = typer.Option(False, "--json", help="Machine-readable output")) -> None:
    """Check own-chrome/li, Chrome's CDP port, LinkedIn login, referral config."""
    config = load_config()
    with ui.spinner("Checking Chrome, own-chrome, and login state..."):
        report = doctor_mod.check(config)
    if json_out:
        _emit_json(report)
    else:
        for check in report["checks"]:
            ui.print_check(check["name"], check["ok"], check.get("detail", ""))
        ui.console.print()
        ui.print_check("overall", report["ok"])
    raise typer.Exit(0 if report.get("ok") else 1)


@app.command()
def scan(json_out: bool = typer.Option(False, "--json", help="Machine-readable output")) -> None:
    """Find threads that still need a reply/referral."""
    config = load_config()
    with ui.spinner("Scanning threads..."):
        candidates = scan_mod.find_referral_candidates(config, port=STATE["port"])
    if json_out:
        _emit_json(dict(candidates))
        return
    rows = [[name, "unread" if c.unread else "read", c.url] for name, c in candidates.items()]
    ui.render_table("Threads needing a reply", ["Name", "Status", "Thread URL"], rows)


@app.command()
def classify(
    text: str,
    name: str = typer.Option("", "--name"),
    headline: str = typer.Option("", "--headline"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Classify a message: hiring? excluded? already referred?"""
    config = load_config()
    reason = classify_mod.exclude_reason(name, headline, text, config)
    result = {
        "hiring": classify_mod.looks_like_hiring(text),
        "excluded": bool(reason),
        "exclude_reason": reason,
        "already_referred": classify_mod.already_referred(text, config),
    }
    if json_out:
        _emit_json(result)
        return
    for key, value in result.items():
        ui.console.print(f"{key}: {value}")


@app.command(name="draft-referral")
def draft_referral_cmd(
    name: str,
    text: str,
    headline: str = typer.Option("", "--headline"),
    reengage: bool = typer.Option(False, "--reengage"),
    stale_days: int = typer.Option(0, "--stale-days"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Draft a referral message. Never touches the browser."""
    config = load_config()
    if not config.referral.enabled:
        ui.console.print("referral is disabled in config; set referral.enabled = true", style="red")
        raise typer.Exit(1)
    draft = copywriter_mod.draft_referral(
        name=name, headline=headline, message=text, config=config, reengage=reengage, stale_days=stale_days
    )
    problems = copywriter_mod.assert_human_copy(draft, config)
    if json_out:
        _emit_json({"draft": draft, "problems": problems})
        raise typer.Exit(0 if not problems else 2)
    ui.draft_panel(draft)
    if problems:
        ui.console.print(f"lint problems: {problems}", style="red")
    raise typer.Exit(0 if not problems else 2)


@app.command(name="send-referral")
def send_referral_cmd(
    name: str,
    url: str,
    text: str = typer.Option("", "--text"),
    stamp: str = typer.Option("", "--stamp"),
    confirm: bool = typer.Option(False, "--confirm", help="Actually click Send. Without this, nothing is sent."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Draft and, only with --confirm, send a referral (text + resume)."""
    config = load_config()
    try:
        with ui.spinner(f"Opening thread for {name}..."):
            result = referral_mod.send_referral_for_candidate(
                name=name, url=url, thread_text=text, config=config, confirm=confirm, stamp=stamp, port=STATE["port"]
            )
    except SendNotConfirmedError as exc:
        _fail_not_confirmed(exc)
        raise typer.Exit(3) from None
    if json_out:
        _emit_json(result)
        raise typer.Exit(0 if not result.skipped else 2)
    if result.skipped:
        ui.print_fail(f"{name}: {result.skipped}")
        raise typer.Exit(2)
    ui.draft_panel(result.draft, title="REFERRAL DRAFT" if not confirm else "REFERRAL SENT")
    ui.print_check("delivered", bool(result.proof and result.proof.get("sent")))
    raise typer.Exit(0)


@message_app.command("read")
def message_read(
    url: str = typer.Option("", "--url"),
    limit: int = typer.Option(40, "--limit"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Read the open thread (or one you name with --url)."""
    config = load_config()
    port = STATE["port"] if STATE["port"] is not None else config.cdp_port
    if url:
        open_thread_fn(url, port)
    with ui.spinner("Reading thread..."):
        data = read_thread_fn(port, limit=limit)
    if json_out:
        _emit_json(data)
        return
    rows = [[str(i + 1), body] for i, body in enumerate(data.get("bodies") or [])]
    ui.render_table(data.get("url", "thread"), ["#", "Message"], rows)


@message_app.command("send")
def message_send(
    text: str,
    attach: Optional[str] = typer.Option(None, "--attach"),
    attach_name: Optional[str] = typer.Option(None, "--attach-name"),
    target: str = typer.Option("", "--target", help="Recipient/thread identity for pacing (governor)."),
    confirm: bool = typer.Option(False, "--confirm", help="Actually click Send. Without this, nothing is sent."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Fill the compose box and, only with --confirm, send."""
    config = load_config()
    try:
        with ui.spinner("Sending..." if confirm else "Drafting..."):
            proof = send_message_fn(
                text=text,
                config=config,
                confirm=confirm,
                attachment_path=attach,
                attachment_name_hint=attach_name,
                port=STATE["port"],
                target=target,
            )
    except SendNotConfirmedError as exc:
        _fail_not_confirmed(exc)
        raise typer.Exit(3) from None
    except RateLimited as exc:
        ui.console.print(str(exc), style="red")
        raise typer.Exit(4) from None
    if json_out:
        _emit_json(proof)
        return
    ui.print_check("sent", proof.get("sent", False))


@post_app.command("draft")
def post_draft(
    text: str,
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Lint post text against the anti-cringe rules. Never touches the browser."""
    problems = post_mod.lint_post(text)
    if json_out:
        _emit_json({"text": text, "problems": problems})
        raise typer.Exit(0 if not problems else 2)
    ui.draft_panel(text, title="POST DRAFT")
    if problems:
        ui.print_fail(f"lint problems: {problems}")
    else:
        ui.print_ok("lint clean")
    raise typer.Exit(0 if not problems else 2)


@post_app.command("publish")
def post_publish(
    text: str,
    image: Optional[str] = typer.Option(None, "--image"),
    confirm: bool = typer.Option(False, "--confirm", help="Actually click Post. Without this, nothing is published."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Fill the composer and, only with --confirm, publish."""
    config = load_config()
    try:
        with ui.spinner("Publishing..." if confirm else "Drafting..."):
            result = post_mod.publish_post(text=text, config=config, confirm=confirm, image_path=image, port=STATE["port"])
    except SendNotConfirmedError as exc:
        _fail_not_confirmed(exc)
        raise typer.Exit(3) from None
    except RateLimited as exc:
        ui.console.print(str(exc), style="red")
        raise typer.Exit(4) from None
    if json_out:
        _emit_json(result)
        return
    ui.print_check("published", result.get("clicked_post", False))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        ui.banner(NAME, __version__, TAGLINE)
        ui.example_panel(EXAMPLES)
        return 0
    if argv[0] in ("--help", "-h"):
        ui.banner(NAME, __version__, TAGLINE)
        ui.example_panel(EXAMPLES)
        ui.console.print()
    try:
        app(args=argv, prog_name="linkedin-agent", standalone_mode=True)
    except SystemExit as exc:
        return int(exc.code or 0)
    except ChromeError as exc:
        ui.print_fail(f"Chrome: {exc}")
        return 1
    return 0  # pragma: no cover -- standalone_mode always raises SystemExit above


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
