"""Command line: argument parsing and `.env` loading only.

WHY THIS EXISTS
---------------
Everything with behaviour lives in `commands/`; this module turns argv and the
environment into a call to it and a process exit code, so the commands stay
testable without a shell.

* API keys come from the environment or a `.env` file in the current directory
  (`KEY=VALUE` lines). The environment wins, so a one-off override never needs
  the file edited. Keys are never printed.
* `enrich` needs `OPENALEX_API_KEY`; `explore` needs `S2_API_KEY`.
  `CROSSREF_MAILTO` and (for enrich) `S2_API_KEY` are optional: without them
  Crossref and Semantic Scholar lookups are skipped.
* `--vault` falls back to `LIT_VAULT_DIR`.
* Exit codes: 0 success, 1 the run failed (an `enrich` note ended in `error`, or
  `explore` could not complete), 2 usage or configuration problem (missing key
  or vault); a 2 makes no network call.
* A note named on the command line is taken relative to the current directory
  when it exists there, else relative to the vault; Obsidian's shell-command
  plugin passes absolute paths, which work either way.
* `main` takes an injectable transport (and `sleep`/`clock`) only so tests never
  touch the network or wait.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from lit_vault_tools.clients.http import Transport, stdlib_transport
from lit_vault_tools.commands.enrich import run_enrich
from lit_vault_tools.commands.explore import run_explore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lit-vault")
    commands = parser.add_subparsers(dest="command", required=True)
    enrich = commands.add_parser("enrich", help="fill graph metadata into saved paper notes")
    enrich.add_argument("--vault", default=None, help="vault directory (default: $LIT_VAULT_DIR)")
    enrich.add_argument("notes", nargs="*", help="notes to enrich (default: every paper note)")
    explore = commands.add_parser("explore", help="write temporary stubs for one paper's references and citations")
    explore.add_argument("--vault", default=None, help="vault directory (default: $LIT_VAULT_DIR)")
    explore.add_argument("note", help="the focus paper note")
    explore.add_argument("--more", action="store_true", help="add the next batch of stubs without wiping")
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


def _need(name: str, env_file: Mapping[str, str]) -> str | None:
    value = _setting(name, env_file)
    if not value:
        print(f"error: {name} is not set (environment or .env)", file=sys.stderr)
    return value


def _vault(args: argparse.Namespace) -> Path | None:
    vault_arg = args.vault or os.environ.get("LIT_VAULT_DIR")
    if not vault_arg:
        print("error: pass --vault or set LIT_VAULT_DIR", file=sys.stderr)
        return None
    return Path(vault_arg)


def main(
    argv: Sequence[str] | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    args = build_parser().parse_args(argv)
    env_file = load_env_file(Path.cwd() / ".env")
    transport = transport or stdlib_transport
    if args.command == "explore":
        return _explore(args, env_file, transport, sleep, clock)
    return _enrich(args, env_file, transport)


def _enrich(args: argparse.Namespace, env_file: Mapping[str, str], transport: Transport) -> int:
    api_key = _need("OPENALEX_API_KEY", env_file)
    vault = _vault(args) if api_key else None
    if not api_key or vault is None:
        return 2
    notes = [_resolve_note(n, vault) for n in args.notes] or None
    summary = run_enrich(
        vault,
        notes,
        api_key,
        transport,
        datetime.date.today(),
        crossref_mailto=_setting("CROSSREF_MAILTO", env_file),
        s2_api_key=_setting("S2_API_KEY", env_file),
    )
    print(
        f"enrich: {summary.ok} ok, {summary.partial} partial, {summary.no_doi} no_doi, "
        f"{summary.not_found} not_found, {summary.error} error"
    )
    return 1 if summary.error else 0


def _explore(
    args: argparse.Namespace,
    env_file: Mapping[str, str],
    transport: Transport,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> int:
    api_key = _need("S2_API_KEY", env_file)
    vault = _vault(args) if api_key else None
    if not api_key or vault is None:
        return 2
    summary = run_explore(
        vault, _resolve_note(args.note, vault), api_key, transport, sleep=sleep, clock=clock, more=args.more
    )
    if not summary.ok:
        print(f"error: {summary.message}", file=sys.stderr)
        return 1
    print(summary.message)
    return 0
