"""
Everything the deployed image runs must parse on the Python it runs on.

Development is on 3.12 and the Space image is `python:3.11-slim`. That gap is
recorded in ADR-023 and it bit immediately: `pages.py` used a backslash inside
an f-string expression, which PEP 701 made legal in 3.12 and which is a
SyntaxError on 3.11. It imported cleanly here, passed every test, deployed, and
killed the container with RUNTIME_ERROR — with no local signal at any point.

A version gap that only shows up in production is exactly the kind of thing a
test should hold, so this parses every shipped file against the deployment
target's grammar.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The directories the Space Dockerfile COPYs. Kept in step with it deliberately:
# if the image starts shipping something else, this list is what has to change.
SHIPPED = ("apps", "services", "packages")

# The `python:` tag in deploy/space/Dockerfile.
DEPLOY_TARGET = (3, 11)


def _shipped_files() -> list[Path]:
    return sorted(f for d in SHIPPED for f in (REPO_ROOT / d).rglob("*.py"))


def test_there_is_something_to_check():
    """A glob that silently matches nothing would make this suite a no-op."""
    assert len(_shipped_files()) > 10


@pytest.mark.parametrize("path", _shipped_files(), ids=lambda p: str(p.name))
def test_shipped_file_parses_on_the_deployment_target(path):
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, feature_version=DEPLOY_TARGET)
    except SyntaxError as exc:
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)}:{exc.lineno} does not parse as Python "
            f"{'.'.join(map(str, DEPLOY_TARGET))}: {exc.msg}\n"
            "It may still run locally on a newer interpreter. The Space image "
            "would fail to start.")


def _f_strings(source: str) -> list[tuple[int, str]]:
    """
    The literal source text of every f-string, with its line number.

    Via the AST, not the tokenizer. `tokenize` was the first attempt and it
    silently found nothing, because Python 3.12 splits f-strings into
    FSTRING_START / MIDDLE / END tokens instead of one STRING — so a filter on
    `tokenize.STRING` skips every f-string on the very interpreter that permits
    the syntax being hunted. Caught by re-injecting the bug and watching the
    test stay green.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.JoinedStr):
            text = ast.get_source_segment(source, node)
            if text:
                out.append((node.lineno, text))
    return out


@pytest.mark.parametrize("path", _shipped_files(), ids=lambda p: str(p.name))
def test_no_f_string_uses_grammar_only_3_12_accepts(path):
    """
    The check that would have caught the outage.

    `ast.parse(..., feature_version=(3, 11))` does NOT reject this. That flag
    gates a short list of grammar features and f-string internals are not among
    them, which was verified by re-injecting the original bug and watching the
    parse test above stay green.

    PEP 701 (3.12) allowed a backslash inside an f-string *replacement field*,
    which was a SyntaxError before it. The Space image runs 3.11.
    """
    offences = []
    for line, text in _f_strings(path.read_text(encoding="utf-8")):
        depth = start = 0
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif ch == "}" and depth:
                depth -= 1
                if depth == 0 and chr(92) in text[start:i]:
                    offences.append(
                        "line {}: backslash inside {{{}}}".format(
                            line, text[start:i].strip()[:46]))
    assert not offences, (
        "{} uses f-string syntax only Python 3.12 accepts, and the Space runs "
        "3.11:\n  {}".format(path.relative_to(REPO_ROOT), "\n  ".join(offences)))


def test_the_dockerfile_still_targets_the_python_this_checks():
    """
    If the image moves to a newer Python, this check must move with it.

    Otherwise it quietly becomes stricter than reality and blocks code that
    would in fact run.
    """
    dockerfile = (REPO_ROOT / "deploy/space/Dockerfile").read_text(encoding="utf-8")
    expected = "python:{}.{}".format(*DEPLOY_TARGET)
    assert expected in dockerfile, (
        f"Dockerfile no longer uses {expected}; update DEPLOY_TARGET in this test")
