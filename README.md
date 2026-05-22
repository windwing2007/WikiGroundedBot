# WikiGroundedBot

A small Claude + Wikipedia grounded QA CLI for the Anthropic prompt engineering take-home.

## Setup

Requirements:

- Python 3.9 or newer
- `pip`
- An Anthropic API key for live answering and eval runs

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
export ANTHROPIC_API_KEY=...
```

Optional model defaults:

```bash
export ANTHROPIC_ANSWER_MODEL=claude-sonnet-4-6
export ANTHROPIC_JUDGE_MODEL=claude-sonnet-4-6
export ANTHROPIC_DEBUG_MODEL=claude-sonnet-4-6
```

## Run

Live mode uses MediaWiki and the Anthropic Messages API. You can either export a key first or let the CLI prompt for one:

```bash
wikigrounded "What is the capital of France?"
```

If `ANTHROPIC_API_KEY` is not set, the CLI asks:

```text
Enter Anthropic API key, or press Enter to use offline demo mode:
```

Pressing Enter intentionally runs that command in offline demo mode. Offline demo mode uses local Wikipedia fixtures plus a deterministic answerer, so it works without an Anthropic API key. Try:

```text
What is the capital of France?
```

Offline mode uses local Wikipedia fixtures and a deterministic answerer, useful for smoke tests:

```bash
wikigrounded --offline "What is the capital of France?"
wikigrounded --offline --demo
wikigrounded --offline
```

When running interactively in a real terminal, the CLI clears the screen on startup and uses color/bold styling to distinguish system messages, user prompts, answers, and metadata. Captured output and non-TTY runs stay plain text. Font size is controlled by your terminal application.

Eval runner. Most evals use the same MediaWiki + Anthropic path as normal answering. Cases that cannot be produced reliably with live services are explicitly marked as simulated:

```bash
wikigrounded eval run
```

If `ANTHROPIC_API_KEY` is not set, `eval run` prompts for a one-time key.

Model listing:

```bash
wikigrounded model
wikigrounded model select
```

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Notes

- The default answer renderer keeps citations simple: answer, search-used badge, and source title footer.
- Fixture-backed tests cover the core UX without requiring network or API keys.
- Normal answering uses `ANTHROPIC_API_KEY`; if absent, the CLI asks for a key or lets you intentionally enter offline demo mode.
