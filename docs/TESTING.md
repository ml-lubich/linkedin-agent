# Testing

## Boundary

The only real I/O boundary in this package is Chrome's CDP socket (via
`own_chrome.cdp` and `linkedin_agent.cdp_session`) and the `li`/`own-chrome`
subprocess calls (via `linkedin_agent.li_cli`). Every test mocks exactly that
boundary — `own_chrome.cdp.evaluate`, `.navigate`, `.describe`, `.pages`,
`.filter_pages`, `.pick_page`, `subprocess.run`, and the raw `socket` module
used by `cdp_session.CdpSession` — and nothing else. Pure logic (config
parsing, classification, copywriting, post linting) is tested directly with
no mocking at all.

No test is skipped or marked `xfail`; a red test means something is broken,
not something to silence.

## Run

```bash
uv run --with-editable . --with pytest --with pytest-cov \
  pytest --cov=linkedin_agent --cov-report=term-missing
```

Target: **>=85% line coverage** across `src/linkedin_agent`.

## What's covered

- `config.py` — TOML parsing, env var overrides, pitch-rule matching.
- `classify.py` — hiring detection, exclusion reasons, already-referred check.
- `copywriter.py` — name/company/role extraction, stale-day parsing, full
  referral drafting, the human-copy lint.
- `scan.py` — candidate-finding loop, with `own_chrome.cdp.evaluate` and
  `linkedin_agent.li_cli.li` mocked.
- `messaging.py` — compose/attach/send/verify, with CDP `evaluate`/`navigate`
  and `cdp_session.set_file_input` mocked; asserts `SendNotConfirmedError` is
  raised whenever `confirm=False`.
- `post.py` — the anti-cringe lint (pure), and publish flow with CDP mocked
  and the same confirm-flag assertion.
- `referral.py` — the full candidate -> draft -> send path, disabled-referral
  short-circuit, and already-referred short-circuit.
- `doctor.py` — every check branch (CDP down, no tab, login page, missing
  referral config), with `shutil.which` and `own_chrome.cdp` mocked.
- `cli.py` — every subcommand's argument wiring and exit code, with the
  underlying module functions monkeypatched.
- `cdp_session.py` — the WebSocket handshake/frame(de)coding and
  `set_file_input`, against a fake in-process socket pair.

## Not covered on purpose

Nothing. If a branch looks uncovered, it is a gap to fix, not a documented
exception — this package is small enough that "mock the boundary and test
the rest for real" covers every path.
