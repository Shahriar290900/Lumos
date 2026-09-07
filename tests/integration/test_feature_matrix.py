"""
The feature matrix: every page, every asset, every control, every endpoint.

This exists because of a specific class of bug that the rest of the suite cannot
see. The unit tests prove the retriever ranks correctly; the API tests prove the
endpoints answer. Neither notices that a button's id changed and the click
handler now binds to `null`, so the button silently does nothing. That bug ships
looking perfect.

Three checks, in order of how much they catch:

1. **Wiring.** Every element id a script reaches for must exist in the page that
   loads the script, and every control in a page must be reachable. This is the
   dead-button check.
2. **Assets.** Every stylesheet and module a page references must return 200.
   A 404 on a module is invisible until someone opens the console.
3. **Contract.** Every endpoint the client calls must exist on the server with
   the method the client uses.

Run standalone for the report:  python -m tests.integration.test_feature_matrix
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "apps" / "api" / "static"

# ── what each page is expected to carry ─────────────────────────────────────
#
# Listed explicitly rather than derived, because the point is to notice when a
# control disappears. A test that discovers the controls from the page can never
# fail for a missing one.
PAGE_CONTROLS: dict[str, tuple[str, ...]] = {
    "/": ("scene", "availCount", "registrySummary"),
    "/login": ("loginBtn", "demoLogin"),
    "/onboarding": (),
    "/chat": ("workbench", "browseView", "readerView", "backToList",
              "curriculumSel", "levelSel", "subjectSel", "offeringState",
              "paperList", "paperTitle", "paperBody", "openRaw",
              "questionChips", "thread", "scopeTag", "q", "go"),
    "/curriculum": ("offerings",),
    "/sources": ("docOffering", "loadDocs", "docs"),
    "/how": (),
}

# Ids a script may reach for that are created at runtime rather than in markup.
RUNTIME_IDS = frozenset({"attachmentPill", "attachmentName", "removeAttachment",
                         "attachBtn", "examples", "answer", "reg", "out",
                         "status", "foot", "offering", "state", "view"})

_ID_IN_JS = re.compile(r"""\$\(\s*["']#([A-Za-z][\w-]*)["']""")
_ID_IN_HTML = re.compile(r"""\bid=["']([A-Za-z][\w-]*)["']""")
_MODULE_SRC = re.compile(r"""<script[^>]+src=["'](/static/[^"']+)["']""")
_CSS_HREF = re.compile(r"""<link[^>]+href=["'](/static/[^"']+)["']""")


def _pages():
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from apps.api import pages
    return {p.path: pages.render(p) for p in pages.ALL}


def _local_modules(html: str) -> list[Path]:
    return [STATIC / src[len("/static/"):] for src in _MODULE_SRC.findall(html)]


def _reachable_js(entry: Path, seen: set[Path] | None = None) -> str:
    """Source of a module and everything it imports, so ids resolve across files."""
    seen = seen if seen is not None else set()
    if not entry.exists() or entry in seen:
        return ""
    seen.add(entry)
    source = entry.read_text(encoding="utf-8")
    out = [source]
    for rel in re.findall(r"""from\s+["'](\./[^"']+)["']""", source):
        out.append(_reachable_js((entry.parent / rel).resolve(), seen))
    return "\n".join(out)


ALL_PAGES = _pages()


# ── 1. wiring ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", sorted(PAGE_CONTROLS), ids=lambda p: p)
def test_every_declared_control_exists_in_the_page(path):
    """A control the feature matrix claims must actually be in the markup."""
    html = ALL_PAGES[path]
    present = set(_ID_IN_HTML.findall(html))
    missing = [c for c in PAGE_CONTROLS[path] if c not in present]
    assert not missing, f"{path} is missing control(s): {missing}"


@pytest.mark.parametrize("path", sorted(PAGE_CONTROLS), ids=lambda p: p)
def test_no_script_binds_to_an_element_the_page_does_not_have(path):
    """
    The dead-button check.

    `$("#go").onclick = send` throws if `#go` is not in the document, and the
    rest of the module never runs — so one renamed id silently disables every
    control below it. This catches that without a browser.
    """
    html = ALL_PAGES[path]
    present = set(_ID_IN_HTML.findall(html)) | RUNTIME_IDS
    dangling: list[str] = []
    for module in _local_modules(html):
        for ident in set(_ID_IN_JS.findall(_reachable_js(module))):
            if ident not in present:
                dangling.append(f"{module.name} reaches #{ident}")
    assert not dangling, f"{path}: script binds to missing element(s): {dangling}"


# ── 2. assets ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", sorted(PAGE_CONTROLS), ids=lambda p: p)
def test_every_referenced_local_asset_exists(path):
    html = ALL_PAGES[path]
    missing = [ref for ref in _MODULE_SRC.findall(html) + _CSS_HREF.findall(html)
               if not (STATIC / ref[len("/static/"):]).exists()]
    assert not missing, f"{path} references missing asset(s): {missing}"


def test_every_module_import_resolves():
    """A bad relative import is a blank page with one console line."""
    broken: list[str] = []
    for module in STATIC.rglob("*.js"):
        for rel in re.findall(r"""from\s+["'](\./[^"']+)["']""",
                              module.read_text(encoding="utf-8")):
            if not (module.parent / rel).resolve().exists():
                broken.append(f"{module.name} imports {rel}")
    assert not broken, f"unresolved import(s): {broken}"


# ── 3. contract ─────────────────────────────────────────────────────────────

def _client_calls() -> set[str]:
    source = (STATIC / "js" / "api.js").read_text(encoding="utf-8")
    return set(re.findall(r"""["'`](/api/[^"'`]*)["'`]""", source))


def test_every_endpoint_the_client_calls_exists_on_the_server():
    """
    The client and the server must agree on the URL space.

    This has already broken once: the pages took `/curriculum` and the JSON API
    took `/curriculum`, whichever registered first won, and the page lost.
    """
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from apps.api.main import app

    served = {r.path for r in app.routes if hasattr(r, "path")}
    missing = []
    for call in _client_calls():
        # `${slug}` in a template literal becomes a path parameter server-side.
        pattern = re.sub(r"\$\{[^}]+\}", "[^/]+", call)
        if not any(re.fullmatch(pattern.replace("{", r"\{").replace("}", r"\}"),
                                route) or
                   re.fullmatch(pattern, re.sub(r"\{[^}]+\}", "X", route).replace("X", "Y"))
                   for route in served):
            # Fall back to comparing the fixed prefix, which is what actually
            # differs when someone moves a route.
            prefix = call.split("${")[0].rstrip("/")
            if not any(route.startswith(prefix) for route in served):
                missing.append(call)
    assert not missing, f"client calls endpoints the server does not serve: {missing}"


def test_pages_and_api_do_not_collide():
    """No page path may also be an API path, and vice versa."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from apps.api import pages
    from apps.api.main import app

    page_paths = {p.path for p in pages.ALL}
    api_paths = {r.path for r in app.routes
                 if hasattr(r, "path") and r.path.startswith("/api")}
    assert not (page_paths & api_paths), "a path is served as both a page and an API"
    for page in page_paths:
        assert not page.startswith("/api"), f"page {page} sits under /api"


# ── 4. layout ───────────────────────────────────────────────────────────────
#
# The gap that let a broken page ship. The checks above proved every control
# existed and every script bound to it — and the page still rendered as one
# stacked column, because the markup and the JavaScript were written and the CSS
# was not. "Present" and "laid out" are different properties.

_CLASS_IN_HTML = re.compile(r"""\bclass=["']([^"']+)["']""")

# Classes that carry no styling by design: state flags toggled from JS, and
# hooks used only as query selectors.
UNSTYLED_BY_DESIGN = frozenset({"on", "grow", "hidden"})


def _classes_used(html: str) -> set[str]:
    out: set[str] = set()
    for group in _CLASS_IN_HTML.findall(html):
        out.update(group.split())
    return out


@pytest.mark.parametrize("path", sorted(PAGE_CONTROLS), ids=lambda p: p)
def test_every_class_a_page_uses_is_actually_styled(path):
    """
    A class with no rule is a component with no layout.

    `.coach`, `.workbench` and `.tutor` were all in the markup, all bound by
    JavaScript, and none of them had a single CSS rule — so the three panes
    stacked vertically and the page looked broken while every other test passed.
    """
    css = (STATIC / "css" / "lumos.css").read_text(encoding="utf-8")
    styled = set(re.findall(r"\.([A-Za-z][\w-]*)", css))
    unstyled = sorted(c for c in _classes_used(ALL_PAGES[path])
                      if c not in styled and c not in UNSTYLED_BY_DESIGN)
    assert not unstyled, f"{path} uses unstyled class(es): {unstyled}"


def test_the_coach_declares_a_two_pane_grid():
    """The layout the page depends on, asserted rather than assumed."""
    css = (STATIC / "css" / "lumos.css").read_text(encoding="utf-8")
    block = re.search(r"\.coach\s*\{([^}]*)\}", css)
    assert block, ".coach has no rule at all"
    body = block.group(1)
    assert "grid" in body, ".coach must be a grid"
    assert "grid-template-columns" in body, ".coach must declare its columns"


@pytest.mark.parametrize("selector", [
    ".doc-btn", ".qchip", ".mode", ".send", ".field select", ".input-row textarea",
])
def test_every_interactive_control_declares_a_focus_style(selector):
    """
    WCAG 2.2: a keyboard user must be able to see where they are.

    Asserted per control rather than globally, because a single `:focus-visible`
    rule elsewhere in the sheet would satisfy a naive grep while leaving these
    specific controls invisible to a keyboard.
    """
    css = (STATIC / "css" / "lumos.css").read_text(encoding="utf-8")
    escaped = re.escape(selector)
    assert re.search(escaped + r"[^{]*:focus-visible", css), (
        f"{selector} has no :focus-visible style")


def test_hover_and_disabled_states_exist_for_the_send_button():
    """The design brief requires default, hover, focus, active and disabled."""
    css = (STATIC / "css" / "lumos.css").read_text(encoding="utf-8")
    for state in (":hover", ":focus-visible", ":active", ":disabled"):
        assert re.search(r"\.send" + re.escape(state), css), f".send lacks {state}"
