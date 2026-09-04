"""
apps.api.pages — the site's pages, as real routes.

Five URLs a browser can bookmark, share and reload: `/`, `/tutor`,
`/curriculum`, `/sources`, `/how`. Not hash fragments over one document —
those cannot be linked to from outside, do not appear in history properly, and
give a search engine nothing.

**Templated in Python, not by a template engine.** The shell is one f-string
and each page contributes a body. That avoids adding Jinja2 to a runtime image
whose whole job is answering questions, and it keeps the markup in the same
place as the route that serves it. If pages ever grow past a handful, that
trade stops paying and a real engine is the answer.

Every page renders complete without JavaScript. Scripts then fill in what needs
the API — availability, answers, document links. A student on a failed CDN sees
a styled, readable page rather than an empty one (ADR-005, ADR-019).
"""

from __future__ import annotations

from dataclasses import dataclass

NAV = (
    ("/", "Home"),
    ("/login", "AI Tutor"),
    ("/curriculum", "Curriculum"),
    ("/sources", "Sources"),
    ("/how", "How it works"),
)

_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;500;600&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/css/lumos.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header>
  <a class="brand" href="/"><span class="sigil">&#10022;</span>
    <span><b>LUMOS</b><small>LEARNERS</small></span></a>
  <nav>{nav}</nav>
  <span class="grow"></span>
  <span id="status">&mdash;</span>
</header>
"""

_FOOT = """<footer><div>
  Lumos &middot; BCOLBD 2026 &middot; Curriculum material is used as retrieval
  context and is never redistributed. Exam papers are shown as published by the
  awarding body; the textbook is not.
  &middot; <a href="https://github.com/Shahriar290900/Lumos">Source</a>
</div></footer>
<script type="module" src="/static/js/app.js"></script>
{scripts}
</body>
</html>
"""


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str
    body: str
    scripts: str = ""
    scene: bool = False


def render(page: Page) -> str:
    # Built without a backslash inside the f-string expression: that is legal
    # from Python 3.12 (PEP 701) and a SyntaxError on 3.11, which is what the
    # Space image runs. It imported fine locally and killed the container.
    def link(href: str, label: str) -> str:
        current = ' aria-current="page"' if href == page.path else ""
        return f'<a href="{href}"{current}>{label}</a>'

    nav = "".join(link(href, label) for href, label in NAV)
    scripts = page.scripts
    if page.scene:
        # three.js is loaded only on the page that draws a scene. Every other
        # page is lighter by ~600 KB for it.
        scripts = ('<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/'
                   'r128/three.min.js"></script>\n' + scripts)
    return (_HEAD.format(title=page.title, description=page.description, nav=nav)
            + page.body
            + _FOOT.format(scripts=scripts))


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

HOME = Page(
    path="/",
    title="Lumos — Lights the Way to Knowledge",
    description=("A curriculum-grounded AI tutor for Bangladeshi students. Every "
                 "citation resolves to a real page in a real document."),
    scene=True,
    scripts='<script type="module" src="/static/js/home.js"></script>',
    body="""
<div class="hero">
  <canvas id="scene" aria-hidden="true"></canvas>
  <div class="hero-inner">
    <p class="kicker">A single spell</p>
    <h1>LUMOS</h1>
    <p class="tagline">LIGHTS THE WAY TO KNOWLEDGE</p>
    <p class="lede">A curriculum-grounded tutor for Bangladeshi students. Every
      citation resolves to a real page in a real document, and insufficient
      evidence produces a stated limitation rather than a confident guess.</p>
    <div class="cta">
      <a class="btn gold" href="/login">Ask the tutor</a>
      <a class="btn ghost" href="/how">How it works</a>
    </div>
    <p class="hint">Move your cursor &middot; <span id="availCount">&mdash;</span></p>
  </div>
</div>

<main id="main">
  <section>
    <h2>Built to be checkable</h2>
    <p class="sub">Most tutors answer confidently and cite nothing. Lumos is the
      other way round: the corpus is declared, the retrieval is measured, and a
      subject it has not indexed says so instead of improvising.</p>
    <div class="grid">
      <div class="card"><div class="ico">&#10022;</div><h3>Grounded</h3>
        <p>Answers come only from a declared curriculum corpus, filtered to your
           subject before anything is ranked.</p></div>
      <div class="card"><div class="ico">&#10070;</div><h3>Cited</h3>
        <p>Every citation is checked against the passages retrieved for that
           question. One that does not resolve is removed.</p></div>
      <div class="card"><div class="ico">&#9672;</div><h3>Bilingual</h3>
        <p>Bangla and English, with retrieval weighted differently for each
           because the two behave differently.</p></div>
      <div class="card"><div class="ico">&#10023;</div><h3>Honest</h3>
        <p>A subject with no corpus is shown as unavailable, with the reasons,
           rather than quietly omitted.</p></div>
    </div>
  </section>

  <section>
    <h2>What is actually indexed</h2>
    <p class="sub">Read from the registry when this page loads, not written by
      hand. If a number here is wrong, the database is wrong.</p>
    <div id="registrySummary" class="grid"></div>
  </section>
</main>
""")

LOGIN = Page(
    path="/login",
    title="Student Login — Lumos",
    description="Log in to access your AI Tutor.",
    scripts='<script type="module" src="/static/js/login.js"></script>',
    body="""
<main id="main">
  <section class="auth-card-wrap">
    <div class="auth-card card">
      <div class="ico" style="text-align:center; font-size:42px; margin-bottom:10px;">&#10022;</div>
      <h2 style="text-align:center">Welcome back</h2>
      <p class="sub" style="text-align:center; max-width:100%">Log in to continue your learning journey.</p>
      
      <div style="display:flex; flex-direction:column; gap:16px; margin-top:30px;">
        <input type="text" placeholder="Student ID or Email" aria-label="Student ID">
        <input type="password" placeholder="Password" aria-label="Password">
        <button id="loginBtn" class="btn gold" style="width:100%; justify-content:center; margin-top:10px">Sign In</button>
      </div>
      
      <div style="text-align:center; margin-top:20px;">
        <p class="meta" style="cursor:pointer" id="demoLogin">Or click here for quick demo login</p>
      </div>
    </div>
  </section>
</main>
""")

ONBOARDING = Page(
    path="/onboarding",
    title="Setup your Curriculum — Lumos",
    description="Select your subjects to personalize your tutor.",
    scripts='<script type="module" src="/static/js/onboarding.js"></script>',
    body="""
<main id="main">
  <div class="page-head">
    <p class="kicker">Onboarding</p>
    <h1>Personalize your Tutor</h1>
    <p class="sub" style="margin-top:10px">Select the exact curriculum and subject you are studying so Lumos can restrict its knowledge base strictly to what you need.</p>
  </div>
  <section>
    <div class="auth-card card" style="max-width: 600px; margin: 0 auto;">
      <h3>Select your subject</h3>
      <p style="margin-bottom:20px; font-size:14px; color:var(--dim)">The tutor will only pull answers from the verified materials for this specific curriculum.</p>
      <select id="offering" aria-label="Subject" style="width:100%; margin-bottom: 20px;"><option>loading&hellip;</option></select>
      <button id="startTutor" class="btn gold" style="width:100%">Start Learning</button>
    </div>
  </section>
</main>
""")

CHAT = Page(
    path="/chat",
    title="AI Tutor Chat — Lumos",
    description="Ask questions and analyze past papers side-by-side.",
    scripts='<script type="module" src="/static/js/chat.js"></script>',
    body="""
<div class="split-layout">
  <!-- Left Pane: Document Viewer -->
  <div class="pane left-pane">
    <div class="pane-header">
      <span class="pill yes">A-Level Physics (2024)</span>
      <span style="font-size:12px; color:var(--dim); margin-left:auto">Paper 4 · Mark Scheme</span>
    </div>
    <div class="doc-viewer" id="docViewer">
      <div class="mock-doc-placeholder">
        <h3>Question 3: Momentum</h3>
        <p><b>(a)</b> State the principle of conservation of momentum. [2]</p>
        <div class="mark-scheme-line"><i>Total momentum before = total momentum after (1)</i></div>
        <div class="mark-scheme-line"><i>Provided no external forces act (1)</i></div>
        <br>
        <p><b>(b)</b> A car of mass 1200kg travelling at 15m/s collides with...</p>
        <div class="mark-scheme-line"><i>Use of m1v1 + m2v2 = (m1+m2)v (1)</i></div>
      </div>
    </div>
  </div>

  <!-- Right Pane: Chatbot -->
  <div class="pane right-pane">
    <div class="chat-history" id="chatHistory">
      <div class="msg tutor">
        <div class="bubble">
          Hello! I am Lumos. I see you are looking at the Physics Paper 4 mark scheme on Momentum. How can I help you understand these concepts?
        </div>
      </div>
    </div>
    
    <div class="chat-input-area">
      <div id="attachmentPill" class="attachment-pill" style="display:none">
        <span class="ico">&#128206;</span> <span id="attachmentName">doc.pdf</span>
        <button id="removeAttachment" class="close-btn">&times;</button>
      </div>
      <div class="input-row">
        <button id="attachBtn" class="attach-btn" title="Upload document">&#128206;</button>
        <input id="q" type="text" placeholder="Ask about this paper..." aria-label="Your question">
        <button id="go" class="gold send-btn">&#10140;</button>
      </div>
    </div>
  </div>
</div>
""")

CURRICULUM = Page(
    path="/curriculum",
    title="Curriculum registry — Lumos",
    description="Which subjects are available, which are not, and exactly why.",
    scripts='<script type="module" src="/static/js/curriculum.js"></script>',
    body="""
<main id="main">
  <div class="page-head">
    <p class="kicker">Coverage</p>
    <h1>Curriculum registry</h1>
    <p class="sub" style="margin-top:10px">The single source of availability. A
      subject is available only with indexed chunks, a known licence and a
      passing evaluation &mdash; never because a card or a route exists.</p>
  </div>
  <section>
    <div id="offerings" class="grid"></div>
  </section>
  <section>
    <h2>Why a subject is blocked</h2>
    <p class="sub">These reasons come from a SQL view, not from application code,
      so the rule that decides cannot drift from the rule that explains.</p>
    <ol class="steps">
      <li><b>indexing_status</b><span>Text exists but is not embedded, so semantic
        retrieval cannot see it.</span></li>
      <li><b>evaluation_status</b><span>Retrieval has not been measured on this
        corpus. An unmeasured corpus is not a working one.</span></li>
      <li><b>licence_status</b><span>The right to use the material has not been
        established. Nothing is published on an unknown licence.</span></li>
      <li><b>publication_status</b><span>A human has not yet decided this subject
        is ready to be offered.</span></li>
    </ol>
  </section>
</main>
""")

SOURCES = Page(
    path="/sources",
    title="Source documents — Lumos",
    description="The exam papers, mark schemes and examiner reports behind the answers.",
    scripts='<script type="module" src="/static/js/sources.js"></script>',
    body="""
<main id="main">
  <div class="page-head">
    <p class="kicker">Provenance</p>
    <h1>Source documents</h1>
    <p class="sub" style="margin-top:10px">Exam papers, mark schemes and examiner
      reports can be opened. The textbook cannot: it grounds answers and is never
      shown, because it is a commercial work rather than freely published exam
      material.</p>
  </div>
  <section>
    <div class="ask">
      <select id="docOffering" aria-label="Subject"><option>loading&hellip;</option></select>
      <button id="loadDocs" class="gold">Show documents</button>
    </div>
    <div id="docs"></div>
  </section>
</main>
""")

HOW = Page(
    path="/how",
    title="How an answer is built — Lumos",
    description="Five stages, each of which can refuse. A refusal is a real answer.",
    body="""
<main id="main">
  <div class="page-head">
    <p class="kicker">Method</p>
    <h1>How an answer is built</h1>
    <p class="sub" style="margin-top:10px">Five stages. Each one can refuse, and a
      refusal is a real answer rather than a failure.</p>
  </div>
  <section>
    <ol class="steps">
      <li><b>Availability</b><span>The registry decides. Nothing downstream runs
        for a subject it has not cleared, and the check is a SQL view rather than
        an <code>if</code> somebody can forget.</span></li>
      <li><b>Retrieval</b><span>Postgres full-text search and pgvector in one
        query, with the curriculum filter applied before ranking rather than
        after. Their rankings are fused with Reciprocal Rank Fusion at
        <code>k=60</code>, which needs no score normalisation between two
        retrievers whose scales are not comparable.</span></li>
      <li><b>Confidence</b><span>Too little evidence produces a stated limitation.
        The search is never widened until something comes back.</span></li>
      <li><b>Generation</b><span>One model, <code>gemma4:e4b</code>. When it is
        unavailable the tutor says so rather than answering from a different
        model, because an answer from an unevaluated model is indistinguishable
        from an evaluated one.</span></li>
      <li><b>Validation</b><span>Every citation is checked against the passages
        retrieved for that question. One that does not resolve is stripped, and
        an answer left with none is not shown as grounded.</span></li>
    </ol>
  </section>
  <section>
    <h2>What it will not do</h2>
    <p class="sub">These are enforced in code and in the schema, not promised in
      prose.</p>
    <div class="grid">
      <div class="card"><h3>Invent a citation</h3><p>A reference that does not
        resolve to this turn's context is removed from the answer.</p></div>
      <div class="card"><h3>Substitute a model</h3><p>There is no fallback chain.
        An unavailable model produces an error, not a quieter answer.</p></div>
      <div class="card"><h3>Answer off-corpus</h3><p>A subject with no indexed
        material is refused before retrieval runs.</p></div>
      <div class="card"><h3>Redistribute sources</h3><p>The tutor explains and
        cites. It does not reproduce the material it read.</p></div>
    </div>
  </section>
</main>
""")

ALL = (HOME, LOGIN, ONBOARDING, CHAT, CURRICULUM, SOURCES, HOW)
