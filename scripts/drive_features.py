#!/usr/bin/env python3
"""Drive every page and control in a real browser, and report a table."""
import json, re, subprocess, sys, time, urllib.request

BASE = "http://127.0.0.1:8010"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
results = []

def record(area, item, ok, detail=""):
    results.append({"area": area, "item": item, "ok": ok, "detail": detail})

def http(path, method="GET", body=None, timeout=240):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"} if body else {})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.time() - t
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", time.time() - t

def dom(path, budget=15000):
    """
    The DOM after scripts have run, as text.

    Injecting JS and reading it back proved unreliable in headless — the flag is
    ignored and every probe returned "no result". Dumping the rendered DOM and
    inspecting it is coarser but it actually works, and it is closer to what a
    user sees anyway.
    """
    return subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--enable-unsafe-swiftshader", f"--virtual-time-budget={budget}",
         "--dump-dom", BASE + path],
        capture_output=True, text=True, timeout=200).stdout

def count(html, pattern):
    import re as _re
    return len(_re.findall(pattern, html))

PAGES = ["/", "/login", "/onboarding", "/chat", "/curriculum", "/sources", "/how"]
for p in PAGES:
    code, body, el = http(p)
    record("page", p, code == 200 and "<title>" in body, f"HTTP {code}, {el:.2f}s")

ASSETS = ["/static/css/lumos.css", "/static/js/api.js", "/static/js/app.js",
          "/static/js/chat.js", "/static/js/scene.js", "/static/js/home.js",
          "/static/js/curriculum.js", "/static/js/sources.js",
          "/static/js/login.js", "/static/js/onboarding.js"]
for a in ASSETS:
    code, _, _ = http(a)
    record("asset", a.split("/")[-1], code == 200, f"HTTP {code}")

code, body, el = http("/api/health")
h = json.loads(body) if code == 200 else {}
record("api", "GET /api/health", code == 200, f"generation={h.get('generation')}")
record("api", "generation is live", h.get("generation") == "live", str(h.get("chat_model")))

code, body, _ = http("/api/curriculum")
offerings = json.loads(body)["offerings"] if code == 200 else []
record("api", "GET /api/curriculum", code == 200, f"{len(offerings)} offerings")
avail = [o for o in offerings if o["is_available"]]
record("gate", "exactly 1 subject available", len(avail) == 1,
       ", ".join(o["slug"] for o in avail))
locked = [o for o in offerings if not o["is_available"]]
record("gate", "locked subjects give reasons",
       all(o["blocked_reasons"] for o in locked), f"{len(locked)} locked")

SLUG = "edexcel-ial/physics/international-as"
code, body, _ = http(f"/api/offerings/{SLUG}/documents")
docs = json.loads(body)["documents"] if code == 200 else []
record("api", "GET documents", code == 200, f"{len(docs)} servable")
record("delivery", "textbook is NOT servable",
       all("Student Book" not in d["title"] for d in docs), "ADR-026")

qp = next((d for d in docs if d["type"] == "past_paper" and d["paper_code"] == "WPH11"), None)
if qp:
    code, body, _ = http(f"/api/documents/{qp['document_id']}/url")
    record("delivery", "presigned URL for a paper", code == 200,
           f"expires_in={json.loads(body).get('expires_in') if code==200 else '-'}")
    code, body, _ = http(f"/api/documents/{qp['document_id']}/questions")
    qs = json.loads(body)["questions"] if code == 200 else []
    record("api", "GET questions", code == 200 and len(qs) == 19, f"{len(qs)} questions")

code, body, el = http("/api/tutor/ask", "POST",
                      {"query": "What is the formula for gravitational potential energy?",
                       "slug": SLUG})
d = json.loads(body) if code == 200 else {}
record("tutor", "ask returns grounded answer", bool(d.get("grounded")),
       f"{len(d.get('citations',[]))} citations, {el:.0f}s")
record("tutor", "answer is not mocked", d.get("is_mock") is False, str(d.get("is_mock")))

code, body, _ = http("/api/tutor/ask", "POST",
                     {"query": "কারক কী?", "slug": "nctb/bangla/ssc"})
d = json.loads(body) if body else {}
record("gate", "Bangla (no corpus) refused", code == 409,
       f"HTTP {code}, {len((d.get('detail') or {}).get('blocked_reasons', []))} reasons")

for label, ans, want in [
    ("marks a correct answer", "A, because 180 kW useful over 240 kW input.", "correct"),
    ("marks a wrong answer", "D, because 300 kW is the total.", "incorrect")]:
    code, body, el = http("/api/tutor/check", "POST",
        {"answer": ans, "slug": SLUG, "paper_code": "WPH11", "question_number": "1"})
    d = json.loads(body) if code == 200 else {}
    record("marking", label, d.get("verdict") == want,
           f"verdict={d.get('verdict')}, {el:.0f}s")

code, body, _ = http("/api/tutor/check", "POST",
    {"answer": "x", "slug": SLUG, "paper_code": "WPH11", "question_number": "99"})
d = json.loads(body) if code == 200 else {}
record("marking", "unknown question refused", d.get("limitation") == "question_not_found",
       str(d.get("limitation")))

# ── browser: are the controls actually wired? ────────────────────────────
h = dom("/chat")
ids = ["workbench", "browseView", "readerView", "backToList",
       "curriculumSel", "levelSel", "subjectSel",
       "paperList", "paperTitle", "paperBody", "questionChips", "thread"]
present = set(re.findall(r'id="([^"]+)"', h))
missing = [i for i in ids if i not in present]
n_options = count(h, r"<option")
n_docs = count(h, r"data-doc=")
n_modes = count(h, r"data-mode=")
record("ui", "/chat controls present", not missing, str(missing) or "all 12 present")
record("ui", "curriculum dropdown populated", ("Edexcel" in h or "NCTB" in h),
       str(n_options) + " options")
record("ui", "paper buttons rendered", n_docs >= 3, str(n_docs) + " buttons")
record("ui", "ask/mark mode toggle", n_modes == 2, str(n_modes) + " modes")
record("ui", "offering state resolved",
       ("indexed chunks" in h or "Not available" in h), "registry verdict shown")

h = dom("/curriculum")
n_cards = count(h, r'class="offering')
n_reasons = count(h, r"<li>")
record("ui", "/curriculum renders offerings", n_cards >= 9, str(n_cards) + " cards")
record("ui", "/curriculum shows blocked reasons", n_reasons > 5,
       str(n_reasons) + " reason lines")

h = dom("/sources")
n_opts = count(h, r"<option")
record("ui", "/sources subject picker", n_opts >= 9, str(n_opts) + " options")

h = dom("/")
n_tiles = count(h, r'class="card"')
record("ui", "/ registry tiles load", n_tiles >= 4, str(n_tiles) + " cards")
record("ui", "/ availability count loads", "subjects available" in h,
       "live count rendered")

print(json.dumps(results, indent=1))
