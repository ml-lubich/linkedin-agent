"""Find LinkedIn threads that still need a reply (or a referral), by reading
the already-open Chrome. Ported from the linkedin-outreach scan.py script,
generalized: the referee/exclusions are Config, not hardcoded names.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from own_chrome.cdp import evaluate

from linkedin_agent.classify import already_referred, exclude_reason
from linkedin_agent.config import Config
from linkedin_agent.li_cli import li

TAB = "linkedin.com"

_SCROLL_JS = (
    "(()=>{const c=document.querySelector('.msg-conversations-container__conversations-list');"
    "if(!c) return false; c.scrollTop=c.scrollHeight;"
    "(c.closest('[class*=scroll]')||c.parentElement).scrollTop=1e9; return true})()"
)


@dataclass
class Candidate:
    name: str
    url: str
    unread: bool
    text: str


def _load_full_thread_list(port: int, rounds: int, sleep_seconds: float) -> None:
    for _ in range(rounds):
        evaluate(port, _SCROLL_JS, TAB)
        if sleep_seconds:
            time.sleep(sleep_seconds)


def _click_thread_js(name: str) -> str:
    import json as _json

    return (
        "(()=>{const a=[...document.querySelectorAll('li.msg-conversation-listitem')]"
        ".find(e=>e.innerText.includes(%s));a&&(a.querySelector('a')||a).click()})()" % _json.dumps(name)
    )


def find_referral_candidates(
    config: Config,
    port: int | None = None,
    thread_limit: int = 500,
    read_limit: int = 80,
    scroll_rounds: int = 15,
    sleep_seconds: float = 2.0,
    click_settle_seconds: float = 2.5,
) -> dict[str, Candidate]:
    """Load every thread, open each one whose preview isn't from us, and keep
    the ones where the last speaker isn't us, the referee isn't mentioned yet,
    and nothing is excluded. Requires the linkedin.com tab and messaging open."""
    cdp_port = port if port is not None else config.cdp_port
    _load_full_thread_list(cdp_port, scroll_rounds, sleep_seconds)

    threads = li("threads", "--limit", str(thread_limit), port=cdp_port).get("threads", [])
    candidates: dict[str, Candidate] = {}
    for thread in threads:
        name = thread.get("name", "")
        preview = thread.get("preview", "")
        if preview.startswith("You"):
            continue
        evaluate(cdp_port, _click_thread_js(name), TAB)
        if click_settle_seconds:
            time.sleep(click_settle_seconds)
        data = li("read", "--limit", str(read_limit), port=cdp_port)
        text = "\n".join(data.get("lines", []))
        speakers = re.findall("View (.+?)’s profile", text)
        first_token = name.split()[0] if name.split() else ""
        if not first_token or first_token not in text or not speakers:
            continue  # click missed, or wrong thread opened
        last_speaker_is_self = bool(config.self_name) and speakers[-1] == config.self_name
        if already_referred(text, config) or last_speaker_is_self:
            continue
        if exclude_reason(name, "", text, config):
            continue
        candidates[name] = Candidate(
            name=name,
            url=data.get("url", ""),
            unread=bool(thread.get("unread")),
            text=text[-2500:],
        )
    return candidates
