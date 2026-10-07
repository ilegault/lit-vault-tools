"""Byte-preserving frontmatter reading and enrichment writing.

WHY THIS EXISTS
---------------
The enrichment script writes into notes the developer has typed into by hand
(invariant 1). Three owners share one file: Zotero Integration owns its
frontmatter fields, the script owns `config.ENRICHMENT_KEYS`, the developer owns
the body. The project adds no runtime dependency, so there is no YAML library:
frontmatter is handled line-wise, and every line that is not an enrichment-owned
line is carried through verbatim, so multi-line Zotero values (`abstract: |`)
and the whole body come out byte-identical.

A note is split into opener / frontmatter lines / closer / body, each holding its
own original line endings, so `split_note(text).render() == text` always. New
lines use the note's own line ending (a CRLF note stays all-CRLF).

`apply_enrichment` semantics:
- `values` is a patch over the owned keys: a key mapped to None is removed, a key
  not mentioned keeps its existing value. Keys outside `ENRICHMENT_KEYS` raise
  ValueError, and so does `enriched_on`, which this module alone decides.
- The owned block is the marker line plus the owned keys in `ENRICHMENT_KEYS`
  order. An existing block is replaced in place; otherwise it is appended at the
  end of the frontmatter. A note with no frontmatter gets a frontmatter block
  holding only the enrichment block; its body is untouched.
- `enriched_on` is `today` when there was no block or any other owned value
  changed, and is kept otherwise. When nothing changed the note is returned
  as-is (even if the developer hand-formatted an owned line), so a re-run is a
  byte-for-byte no-op (invariant 4).
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lit_vault_tools.config import ENRICHMENT_KEYS

MARKER = "# ---- enrichment-script-owned ----"
_ENRICHED_ON = "enriched_on"
_SAFE_SCALAR = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")

Value = str | Sequence[str] | None


@dataclass(frozen=True)
class NoteParts:
    """A note split into regions; each string keeps its original line endings."""

    opener: str
    lines: tuple[str, ...]
    closer: str
    body: str
    eol: str

    def render(self) -> str:
        return self.opener + "".join(self.lines) + self.closer + self.body


def _eol_of(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def split_note(text: str) -> NoteParts:
    """Split a note into frontmatter lines and body. Unclosed frontmatter is all body."""
    lines = text.splitlines(keepends=True)
    default_eol = "\r\n" if "\r\n" in text else "\n"
    if lines and lines[0].rstrip("\r\n") == "---" and _eol_of(lines[0]):
        for index in range(1, len(lines)):
            if lines[index].rstrip("\r\n") == "---":
                return NoteParts(
                    opener=lines[0],
                    lines=tuple(lines[1:index]),
                    closer=lines[index],
                    body="".join(lines[index + 1 :]),
                    eol=_eol_of(lines[0]),
                )
    return NoteParts(opener="", lines=(), closer="", body=text, eol=default_eol)


def _key_of(line: str) -> str | None:
    """The key a column-0 `key: value` line defines, else None."""
    if not line or line[0] in " \t#-":
        return None
    key, colon, _ = line.partition(":")
    return key.strip() if colon and key.strip() else None


def _value_text(line: str) -> str:
    """The text after `key:`, line ending and trailing comment removed."""
    return _strip_comment(line.partition(":")[2].rstrip("\r\n")).strip()


def _strip_comment(text: str) -> str:
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index]
    return text


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            try:
                return json.loads(text)
            except ValueError:
                return inner
        return inner.replace("''", "'")
    return text


def _split_flow(text: str) -> list[str]:
    """Split the inside of `[a, "b, c"]` on top-level commas."""
    items, current, quote = [], [], None
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [_unquote(item) for item in items if item.strip()]


def _continuation(lines: Sequence[str], start: int) -> list[str]:
    """Lines belonging to the key at `start`: indented lines or `- ` block items."""
    out = []
    for line in lines[start + 1 :]:
        if line[:1] in (" ", "\t") or line.startswith("- "):
            out.append(line)
        else:
            break
    return out


def _find(lines: Sequence[str], key: str) -> int | None:
    for index, line in enumerate(lines):
        if _key_of(line) == key:
            return index
    return None


def read_scalar(parts: NoteParts, key: str) -> str | None:
    """Value of a column-0 `key:` line, quotes and trailing comment stripped; None if absent."""
    index = _find(parts.lines, key)
    if index is None:
        return None
    value = _value_text(parts.lines[index])
    return _unquote(value) if value else None


def read_list(parts: NoteParts, key: str) -> list[str]:
    """Items of an inline `[...]` or block `- item` list; [] when absent or empty."""
    index = _find(parts.lines, key)
    if index is None:
        return []
    value = _value_text(parts.lines[index])
    if value.startswith("[") and value.endswith("]"):
        return _split_flow(value[1:-1])
    if value:
        return [_unquote(value)]
    items = []
    for line in _continuation(parts.lines, index):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(_unquote(_strip_comment(stripped[2:]).strip()))
    return items


def _existing_owned(parts: NoteParts) -> dict[str, str | list[str]]:
    """Owned keys currently in the note, parsed to comparable values."""
    found: dict[str, str | list[str]] = {}
    for key in ENRICHMENT_KEYS:
        index = _find(parts.lines, key)
        if index is None:
            continue
        value = _value_text(parts.lines[index])
        if value.startswith("[") or not value:
            found[key] = read_list(parts, key)
        else:
            found[key] = _unquote(value)
    return found


def _normalize(value: str | Sequence[str]) -> str | list[str]:
    return str(value) if isinstance(value, str) else [str(item) for item in value]


def _format_scalar(value: str) -> str:
    return value if _SAFE_SCALAR.match(value) else json.dumps(value, ensure_ascii=False)


def _format_line(key: str, value: str | list[str], eol: str) -> str:
    if isinstance(value, list):
        rendered = "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
    else:
        rendered = _format_scalar(value)
    return f"{key}: {rendered}{eol}"


def apply_enrichment(parts: NoteParts, values: Mapping[str, Value], today: datetime.date | str) -> NoteParts:
    """Return `parts` with the owned block patched by `values`; see the module docstring."""
    unknown = [key for key in values if key not in ENRICHMENT_KEYS or key == _ENRICHED_ON]
    if unknown:
        raise ValueError(f"not enrichment-writable keys: {', '.join(sorted(unknown))}")

    existing = _existing_owned(parts)
    final = dict(existing)
    for key, value in values.items():
        if value is None:
            final.pop(key, None)
        else:
            final[key] = _normalize(value)

    existing_values = {k: v for k, v in existing.items() if k != _ENRICHED_ON}
    final_values = {k: v for k, v in final.items() if k != _ENRICHED_ON}
    if _ENRICHED_ON in existing and existing_values == final_values:
        return parts
    final_values[_ENRICHED_ON] = today.isoformat() if isinstance(today, datetime.date) else str(today)

    block = [MARKER + parts.eol]
    block += [_format_line(key, final_values[key], parts.eol) for key in ENRICHMENT_KEYS if key in final_values]

    kept: list[str] = []
    insert_at: int | None = None
    skip: set[int] = set()
    for index, line in enumerate(parts.lines):
        if index in skip:
            continue
        key = _key_of(line)
        if key in ENRICHMENT_KEYS:
            skip.update(range(index + 1, index + 1 + len(_continuation(parts.lines, index))))
        elif line.rstrip("\r\n") != MARKER:
            kept.append(line)
            continue
        if insert_at is None:
            insert_at = len(kept)
    if insert_at is None:
        insert_at = len(kept)
    new_lines = tuple(kept[:insert_at] + block + kept[insert_at:])

    if parts.opener:
        return NoteParts(parts.opener, new_lines, parts.closer, parts.body, parts.eol)
    rule = "---" + parts.eol
    return NoteParts(rule, new_lines, rule, parts.body, parts.eol)


def set_key_line(parts: NoteParts, key: str, rendered: str) -> NoteParts:
    """Set one non-enrichment key (`aliases`, `location`) on a person/place note.

    The `key: rendered` line replaces the key's existing line (and its block
    continuation) in place, or is appended at the end of the frontmatter. Every
    other line and the body are carried through verbatim. A note without
    frontmatter is returned unchanged: this is only used on notes the script
    itself created, whose identity was already read from frontmatter.
    """
    if not parts.opener:
        return parts
    line = f"{key}: {rendered}{parts.eol}"
    index = _find(parts.lines, key)
    if index is None:
        return NoteParts(parts.opener, (*parts.lines, line), parts.closer, parts.body, parts.eol)
    end = index + 1 + len(_continuation(parts.lines, index))
    lines = (*parts.lines[:index], line, *parts.lines[end:])
    return NoteParts(parts.opener, lines, parts.closer, parts.body, parts.eol)
