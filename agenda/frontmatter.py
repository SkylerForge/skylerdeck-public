"""Flat YAML frontmatter for cards and projects.

The header is a contract with agents and scripts: one `key: value` per line, values on
a single line. Free text and lists are written as JSON (a JSON string or array is
valid YAML), so any YAML parser reads the header back unchanged, and so does a regex.
"""
from __future__ import annotations

import hashlib
import json
import re

FRONT_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
LINE_RE = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*?)[ \t]*$")
# Values safe to write without quotes: they read back as the same string, a date or an int.
PLAIN_RE = re.compile(r"^(?:[A-Za-z][\w.-]*|\d{4}-\d{2}-\d{2}|[1-9]\d{0,5})$")
YAML_WORDS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n"}

Valor = str | list[str]


def _scalar(raw: str) -> str:
    if raw.startswith('"'):
        try:
            return str(json.loads(raw))
        except ValueError:
            return raw.strip('"')
    if raw.startswith("'"):
        return raw[1:-1].replace("''", "'") if len(raw) > 1 and raw.endswith("'") else raw[1:]
    return "" if raw in ("", "~", "null") else raw


def _value(raw: str) -> Valor:
    if raw.startswith("["):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(i) for i in items]
        except ValueError:
            pass
        inner = raw[1:-1] if raw.endswith("]") else raw[1:]
        return [_scalar(part.strip()) for part in inner.split(",") if part.strip()]
    return _scalar(raw)


def parse(text: str) -> tuple[dict[str, Valor], str]:
    """Returns (fields, body). Text without a header is all body."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    fields: dict[str, Valor] = {}
    for line in m.group(1).splitlines():
        kv = LINE_RE.match(line)
        if kv:
            fields[kv.group(1)] = _value(kv.group(2))
    return fields, text[m.end():]


def one_line(value: object) -> str:
    return " ".join(str(value if value is not None else "").split())


def _format(key: str, value: Valor, plain_keys: set[str]) -> str:
    if isinstance(value, list):
        return json.dumps([one_line(v) for v in value], ensure_ascii=False)
    if key in plain_keys and PLAIN_RE.match(value) and value.lower() not in YAML_WORDS:
        return value
    return json.dumps(value, ensure_ascii=False)


def serialize(fields: dict[str, Valor], body: str, order: list[str], plain_keys: set[str]) -> str:
    keys = [k for k in order if k in fields] + [k for k in fields if k not in order]
    lines = []
    for key in keys:
        value = fields[key]
        value = [one_line(v) for v in value if one_line(v)] if isinstance(value, list) else one_line(value)
        if value:
            lines.append(f"{key}: {_format(key, value, plain_keys)}")
    rest = body.lstrip("\n").rstrip()
    return f"---\n" + "\n".join(lines) + f"\n---\n\n{rest}\n"


def version_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ---------- body sections ----------

def _section_re(title: str) -> re.Pattern:
    return re.compile(rf"^## {re.escape(title)}[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def section(body: str, title: str) -> str | None:
    m = _section_re(title).search(body)
    return m.group(1).strip("\n") if m else None


def set_section(body: str, title: str, content: str, before: str | None = None) -> str:
    """Replaces a `## title` section, or adds it (before `## before` if given, else at the end)."""
    block = f"## {title}\n\n{content.strip()}\n\n" if content.strip() else f"## {title}\n\n"
    rx = _section_re(title)
    if rx.search(body):
        return rx.sub(lambda _: block, body, count=1)
    if before:
        m = re.search(rf"^## {re.escape(before)}[ \t]*$", body, re.MULTILINE)
        if m:
            return body[: m.start()] + block + body[m.start():]
    return body.rstrip() + "\n\n" + block


def append_to_section(body: str, title: str, line: str) -> str:
    current = section(body, title)
    content = f"{current}\n{line}" if current else line
    return set_section(body, title, content)
