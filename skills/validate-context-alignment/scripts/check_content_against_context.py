#!/usr/bin/env python3
"""
check_content_against_context.py — verify that a built file (landing page,
talent-registration form, etc.) actually contains the literal Nexova content
required by CONTEXT.md: section copy, form field labels, exact validation
error messages, the success message, the company-vs-candidate restriction
message, and the Schema.org Organization JSON-LD block.

This script PARSES CONTEXT.md at run time — it never hardcodes a duplicate
copy of the brief — so if CONTEXT.md changes (new field, reworded error
message, updated JSON-LD), the requirements this script checks change with
it automatically.

Usage:
    python3 check_content_against_context.py <target_file> [<target_file> ...]
    python3 check_content_against_context.py --combine <target> [<target> ...]
    python3 check_content_against_context.py --dump-requirements
    python3 check_content_against_context.py --context path/to/CONTEXT.md <target_file>

Args:
    target_file          One or more built files (HTML/JS/TSX/...) to check.
                          Required unless --dump-requirements is given. Each
                          is checked SEPARATELY — every one must, on its own,
                          contain everything required.
    --combine             Treat all given targets as one combined page instead
                          of checking each separately. A target may be a file
                          or a directory (directories are read recursively,
                          restricted to *.html/*.js/*.jsx/*.ts/*.tsx, skipping
                          node_modules/dist/.git) and every matched file's
                          text is concatenated before checking. Use this for
                          a component-based app (e.g. a React SPA) where the
                          required copy is split across several source files
                          instead of living in one static HTML file — e.g.
                          `--combine uis/website/index.html uis/website/src`.
    --context <path>     Path to CONTEXT.md. Defaults to CONTEXT.md at the
                          repo root (three levels up from this script).
    --dump-requirements  Print every requirement extracted from CONTEXT.md
                          as JSON and exit 0, without checking any file.
                          Useful to sanity-check the parser itself.

Exit codes:
    0   All required literal strings were found in the target file(s)
        (or --dump-requirements ran successfully).
    1   At least one required item is missing, or CONTEXT.md/target files
        could not be read/parsed.

No third-party dependencies — stdlib only.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

DEFAULT_CONTEXT_PATH = Path(__file__).resolve().parents[3] / "CONTEXT.md"

COMBINE_EXTENSIONS = {".html", ".js", ".jsx", ".ts", ".tsx"}
COMBINE_SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__"}


def _iter_combine_files(target: Path):
    """Yield files to read for --combine: the file itself, or every matching
    file under a directory (recursive, deterministic order, skipping build/
    dependency directories)."""
    if target.is_file():
        yield target
        return
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path.suffix not in COMBINE_EXTENSIONS:
            continue
        if COMBINE_SKIP_DIRS & set(path.relative_to(target).parts):
            continue
        yield path


def _section(text: str, heading: str) -> str:
    """Return the text of a `## heading` (or `### heading`) section, up to the
    next heading of the same or higher level, or the next `---` rule."""
    pattern = re.compile(
        rf"^#{{2,3}}\s+{re.escape(heading)}\s*$(.*?)(?=^#{{1,3}}\s+|^---\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


def _strip_md(s: str) -> str:
    """Remove bold markers and angle brackets (markdown autolink syntax) from
    a piece of extracted text, since rendered/coded output won't have them."""
    return s.replace("**", "").replace("<", "").replace(">", "").strip()


def _pipe_split(s: str) -> list[str]:
    return [part.strip() for part in s.split("|") if part.strip()]


def extract_schema_org(text: str) -> dict:
    section = _section(text, "Schema.org markup requerido")
    match = re.search(r"```json\s*(.*?)\s*```", section, re.DOTALL)
    if not match:
        raise ValueError("No JSON-LD fenced code block found under 'Schema.org markup requerido'")
    return json.loads(match.group(1))


def extract_form_fields(text: str) -> list[str]:
    section = _section(text, "Campos del formulario de registro de talento")
    return [_strip_md(m) for m in re.findall(r"^\|\s*\*\*(.+?)\*\*\s*\|", section, re.MULTILINE)]


def extract_error_messages(text: str) -> list[dict]:
    """Returns [{'field': ..., 'message': ..., 'dynamic_suffix': bool}, ...].
    'message' is truncated before a dynamic placeholder like '(quedan X)'."""
    section = _section(text, "Mensajes de error esperados")
    results = []
    for field, message in re.findall(r'^-\s*\*\*(.+?):\*\*\s*"(.+?)"\s*$', section, re.MULTILINE):
        dynamic = "(quedan X)" in message
        if dynamic:
            message = message.split(" (quedan")[0]
        results.append({"field": field.strip(), "message": _strip_md(message), "dynamic_suffix": dynamic})
    return results


def extract_success_message(text: str) -> list[str]:
    section = _section(text, "Mensaje de éxito")
    lines = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line.startswith(">"):
            line = _strip_md(line.lstrip(">").strip())
            if line:
                lines.append(line)
    return lines


def extract_restriction_message(text: str) -> str:
    section = _section(text, "Restricción específica")
    match = re.search(r'"([^"]+)"', section)
    return _strip_md(match.group(1)) if match else ""


def extract_contact_info(text: str) -> dict:
    section = _section(text, "Contacto")
    info = {}
    for label, value in re.findall(r"^-\s*(Email|Valencia|Miami):\s*(.+)$", section, re.MULTILINE):
        info[label] = _strip_md(value)
    return info


def extract_footer(text: str) -> list[str]:
    section = _section(text, "Footer")
    items = []
    for raw_line in section.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue
        items.extend(_pipe_split(line) if "|" in line else [_strip_md(line)])
    return items


def extract_header(text: str) -> list[str]:
    section = _section(text, "Header")
    items = []
    for raw_line in section.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if line.lower().startswith("navegación:"):
            items.extend(_pipe_split(line.split(":", 1)[1]))
        elif line:
            quoted = re.search(r'"([^"]+)"', line)
            items.append(_strip_md(quoted.group(1)) if quoted else _strip_md(line))
    return items


def extract_hero(text: str) -> dict:
    section = _section(text, "Hero")
    hero = {}
    for key, pattern in {
        "titular": r'\*\*Titular:\*\*\s*"([^"]+)"',
        "subtitulo": r'\*\*Subt[ií]tulo:\*\*\s*"([^"]+)"',
        "cta": r'\*\*Call to action:\*\*.*?"([^"]+)"',
    }.items():
        match = re.search(pattern, section)
        if match:
            hero[key] = _strip_md(match.group(1))
    return hero


def extract_services(text: str) -> list[dict]:
    section = _section(text, "Servicios (3 columnas)")
    services = []
    current = None
    for raw_line in section.splitlines():
        title_match = re.match(r"^\d+\.\s*\*\*(.+?)\*\*\s*$", raw_line.strip())
        bullet_match = re.match(r"^\s+-\s+(.+)$", raw_line)
        if title_match:
            current = {"title": _strip_md(title_match.group(1)), "bullets": []}
            services.append(current)
        elif bullet_match and current is not None:
            current["bullets"].append(_strip_md(bullet_match.group(1)))
    return services


def extract_why_nexova(text: str) -> list[str]:
    section = _section(text, "Por qué Nexova (2 columnas)")
    return [_strip_md(m) for m in re.findall(r"^-\s+(.+)$", section, re.MULTILINE)]


def extract_all(context_text: str) -> dict:
    return {
        "schema_org": extract_schema_org(context_text),
        "form_fields": extract_form_fields(context_text),
        "error_messages": extract_error_messages(context_text),
        "success_message": extract_success_message(context_text),
        "restriction_message": extract_restriction_message(context_text),
        "contact_info": extract_contact_info(context_text),
        "footer": extract_footer(context_text),
        "header": extract_header(context_text),
        "hero": extract_hero(context_text),
        "services": extract_services(context_text),
        "why_nexova": extract_why_nexova(context_text),
    }


def _flatten_strings(value) -> list[str]:
    """Recursively collect every string leaf from a nested dict/list."""
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_flatten_strings(v))
    return out


def _find_ld_json_blocks(source: str) -> list[dict]:
    blocks = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        source,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            blocks.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return blocks


def _prose_text(raw: str) -> str:
    """Normalize markup-bearing source for literal prose/label matching:
    strip HTML/JSX tags, decode HTML entities, and collapse whitespace runs
    (including newlines/indentation) to a single space. Component-based UIs
    split one visible sentence across inline tags (`<strong>X</strong> Y`
    still reads as "X Y"), wrap long text across source lines (JSX collapses
    that whitespace when rendering, same as HTML), and sometimes write
    `&copy;` instead of the literal "©" — all render correctly but defeat a
    naive raw-text substring check. Not used for the Schema.org check, which
    parses <script> blocks from the raw source directly."""
    unescaped = html.unescape(re.sub(r"<[^>]*>", "", raw))
    return re.sub(r"\s+", " ", unescaped)


def check_target(target_text: str, requirements: dict) -> list[str]:
    """Return a list of human-readable descriptions of missing requirements."""
    missing = []

    # Schema.org: compare as data, not as raw text, so formatting doesn't matter.
    ld_blocks = _find_ld_json_blocks(target_text)
    if not ld_blocks:
        missing.append("Schema.org: no <script type=\"application/ld+json\"> block found")
    elif requirements["schema_org"] not in ld_blocks:
        expected_values = set(_flatten_strings(requirements["schema_org"]))
        found_values = set()
        for block in ld_blocks:
            found_values |= set(_flatten_strings(block))
        for value in sorted(expected_values - found_values):
            missing.append(f"Schema.org: missing/incorrect value '{value}'")

    # Everything else is prose/labels: match against tag-stripped,
    # entity-decoded text so inline markup and named entities don't produce
    # false negatives (see _prose_text).
    prose_text = _prose_text(target_text)

    for field in requirements["form_fields"]:
        if field not in prose_text:
            missing.append(f"Form field label not found: '{field}'")

    for item in requirements["error_messages"]:
        msg = item["message"]
        if msg not in prose_text:
            missing.append(f"Error message not found for '{item['field']}': \"{msg}\"")
        elif item["dynamic_suffix"] and "quedan" not in prose_text.lower():
            missing.append(
                f"Error message for '{item['field']}' found, but no live 'quedan N' "
                f"remaining-characters counter text was found nearby"
            )

    for line in requirements["success_message"]:
        if line not in prose_text:
            missing.append(f"Success message line not found: \"{line}\"")

    if requirements["restriction_message"] and requirements["restriction_message"] not in prose_text:
        missing.append(f"Restriction message not found: \"{requirements['restriction_message']}\"")

    for label, value in requirements["contact_info"].items():
        if value not in prose_text:
            missing.append(f"Contact info not found ({label}): '{value}'")

    for item in requirements["footer"]:
        if item not in prose_text:
            missing.append(f"Footer content not found: '{item}'")

    for item in requirements["header"]:
        if item not in prose_text:
            missing.append(f"Header content not found: '{item}'")

    for key, value in requirements["hero"].items():
        if value not in prose_text:
            missing.append(f"Hero {key} not found: \"{value}\"")

    for service in requirements["services"]:
        if service["title"] not in prose_text:
            missing.append(f"Service title not found: '{service['title']}'")
        for bullet in service["bullets"]:
            if bullet not in prose_text:
                missing.append(f"Service bullet not found ('{service['title']}'): '{bullet}'")

    for item in requirements["why_nexova"]:
        if item not in prose_text:
            missing.append(f"'Por qué Nexova' bullet not found: '{item}'")

    return missing


def main() -> int:
    args = sys.argv[1:]
    context_path = DEFAULT_CONTEXT_PATH
    if "--context" in args:
        idx = args.index("--context")
        context_path = Path(args[idx + 1])
        args = args[:idx] + args[idx + 2 :]

    dump_only = "--dump-requirements" in args
    if dump_only:
        args = [a for a in args if a != "--dump-requirements"]

    combine = "--combine" in args
    if combine:
        args = [a for a in args if a != "--combine"]

    if not context_path.exists():
        print(f"ERROR: CONTEXT.md not found at {context_path}", file=sys.stderr)
        return 1

    context_text = context_path.read_text(encoding="utf-8")

    try:
        requirements = extract_all(context_text)
    except Exception as exc:  # noqa: BLE001 - surface any parse failure clearly
        print(f"ERROR: failed to parse {context_path}: {exc}", file=sys.stderr)
        return 1

    if dump_only:
        print(json.dumps(requirements, indent=2, ensure_ascii=False))
        return 0

    if not args:
        print("ERROR: no target file given. Pass at least one file to check, "
              "or use --dump-requirements.", file=sys.stderr)
        return 1

    if combine:
        label = "--combine " + " ".join(args)
        texts = []
        for target_arg in args:
            target_path = Path(target_arg)
            if not target_path.exists():
                print(f"FAIL  {label}\n      - path does not exist: {target_arg}")
                return 1
            for file_path in _iter_combine_files(target_path):
                texts.append(file_path.read_text(encoding="utf-8", errors="replace"))
        target_text = "\n".join(texts)
        missing = check_target(target_text, requirements)

        if missing:
            print(f"FAIL  {label}  ({len(missing)} missing)")
            for item in missing:
                print(f"      - {item}")
            return 1
        print(f"OK    {label}")
        return 0

    exit_code = 0
    for target_arg in args:
        target_path = Path(target_arg)
        if not target_path.exists():
            print(f"FAIL  {target_arg}\n      - file does not exist")
            exit_code = 1
            continue

        target_text = target_path.read_text(encoding="utf-8", errors="replace")
        missing = check_target(target_text, requirements)

        if missing:
            exit_code = 1
            print(f"FAIL  {target_arg}  ({len(missing)} missing)")
            for item in missing:
                print(f"      - {item}")
        else:
            print(f"OK    {target_arg}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
