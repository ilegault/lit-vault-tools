"""Command line: argument parsing and `.env` loading only.

WHY THIS EXISTS
---------------
Everything with behaviour lives in `commands/`; this module turns argv and the
environment into a call to it and a process exit code, so the commands stay
testable without a shell.

* API keys come from the environment or a `.env` file in the current directory
  (`KEY=VALUE` lines). The environment wins, so a one-off override never needs
  the file edited. Keys are never printed.
* `--vault` falls back to `LIT_VAULT_DIR`.
* Exit codes: 0 success, 1 at least one note ended in `error`, 2 usage or
  configuration problem (missing key or vault); a 2 makes no network call.
* A note named on the command line is taken relative to the current directory
  when it exists there, else relative to the vault; Obsidian's shell-command
  plugin passes absolute paths, which work either way.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from lit_vault_tools.clients.http import Transport, stdlib_transport
from lit_vault_tools.commands.enrich import run_enrich


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lit-vault")
    commands = parser.add_subparsers(dest="command", required=True)
    enrich = commands.add_parser("enrich", help="fill graph metadata into saved paper notes")
    enrich.add_argument("--vault", default=None, help="vault directory (default: $LIT_VAULT_DIR)")
    enrich.add_argument("notes", nargs="*", help="notes to enrich (default: every paper note)")
    return parser


def load_env_file(path: Path) -> dict[str, str]:
    """Parse `KEY=VALUE` lines; blank lines and `#` comments are ignored."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _setting(name: str, env_file: Mapping[str, str]) -> str | None:
    return os.environ.get(name) or env_file.get(name) or None


def _resolve_note(raw: str, vault: Path) -> Path:
    path = Path(raw)
    if path.is_absolute() or path.exists():
        return path
    return vault / path


def main(argv: Sequence[str] | None = None, transport: Transport | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_file = load_env_file(Path.cwd() / ".env")
    api_key = _setting("OPENALEX_API_KEY", env_file)
    if not api_key:
        print("error: OPENALEX_API_KEY is not set (environment or .env)", file=sys.stderr)
        return 2
    vault_arg = args.vault or os.environ.get("LIT_VAULT_DIR")
    if not vault_arg:
        print("error: pass --vault or set LIT_VAULT_DIR", file=sys.stderr)
        return 2
    vault = Path(vault_arg)
    notes = [_resolve_note(n, vault) for n in args.notes] or None
    summary = run_enrich(vault, notes, api_key, transport or stdlib_transport, datetime.date.today())
    print(
        f"enrich: {summary.ok} ok, {summary.no_doi} no_doi, {summary.not_found} not_found, {summary.error} error"
    )
    return 1 if summary.error else 0
