#!/usr/bin/env python3
"""Synthetic-user browser harness: one persona agent drives one real browser.

One command per invocation; each user has a persistent Chromium profile so
cookies, localStorage, usage meters and sessions survive between steps.
Every step appends to runs/<run>/<user>/trace.jsonl (durable, append-only) and
saves a viewport screenshot + full page text as evidence.

Usage:
  browse.py <user> init --device desktop|mobile [--profile-from <dir>]
  browse.py <user> goto <url>               # paths printed are absolute
  browse.py <user> more                      # next chunk of current page text
  browse.py <user> act '<json steps>'        # in-page interaction on current URL
        steps: [{"fill": "<label|placeholder|css>", "value": "..."},
                {"click": "<visible text|css>"}, {"press": "Enter"},
                {"select": "<label|css>", "value": "..."},
                {"scroll": 1500}, {"wait": 1500}]
  browse.py <user> shot [--full]             # screenshot path for visual review
  browse.py <user> end <clean|failed|abandoned> "<note>"

Traffic is tagged with a User-Agent suffix (SYNTH_UA_TAG) so it can be
filtered out of the target site's analytics.

Environment:
  SYNTH_RUN     run name; evidence goes to runs/<run>/<user>/   (default: run-local)
  SYNTH_HOME    where runs/ and profiles/ live                   (default: this folder)
  SYNTH_UA_TAG  User-Agent suffix                                (default: SyntheticUser/1.0 (origin=verification))
  SYNTH_CHUNK   characters of page text per printed chunk        (default: 3200)
  SYNTH_HEADED  set to 1 to watch the browser

Browser profiles live at profiles/<run>/<user>, so every run starts as a true
first visit. Each command relaunches the browser and reloads the current URL:
in-page state (open dialogs, typed values) does not carry between calls, so a
multi-step interaction goes in one `act` list.
"""
import json, os, sys, time, re, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(os.environ.get("SYNTH_HOME") or Path(__file__).resolve().parent)
RUN = os.environ.get("SYNTH_RUN", "run-local")
UA_TAG = os.environ.get("SYNTH_UA_TAG", "SyntheticUser/1.0 (origin=verification)")
CHUNK = int(os.environ.get("SYNTH_CHUNK", "3200"))

def udir(user):
    d = ROOT / "runs" / RUN / user
    (d / "shots").mkdir(parents=True, exist_ok=True)
    (d / "pages").mkdir(parents=True, exist_ok=True)
    return d

def load_state(user):
    p = udir(user) / "state.json"
    return json.loads(p.read_text()) if p.exists() else {}

def save_state(user, st):
    (udir(user) / "state.json").write_text(json.dumps(st, indent=1))

def trace(user, rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec["origin"] = "verification"
    with open(udir(user) / "trace.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")

PERF_JS = """() => {
  const n = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource');
  let kb = (n.transferSize||0); res.forEach(r => kb += (r.transferSize||0));
  return {ttfb: Math.round(n.responseStart||0), dcl: Math.round(n.domContentLoadedEventEnd||0),
          load: Math.round(n.loadEventEnd||0), lcp: Math.round(window.__lcp||0),
          cls: Math.round((window.__cls||0)*1000)/1000,
          kb: Math.round(kb/1024), requests: res.length+1,
          overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
          height: document.documentElement.scrollHeight};
}"""
INIT_JS = """
window.__lcp=0; window.__cls=0;
try{new PerformanceObserver(l=>{for(const e of l.getEntries()) window.__lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});}catch(e){}
try{new PerformanceObserver(l=>{for(const e of l.getEntries()) if(!e.hadRecentInput) window.__cls+=e.value}).observe({type:'layout-shift',buffered:true});}catch(e){}
"""
VIEW_JS = """() => {
  const clean = s => (s||'').replace(/\\s+/g,' ').trim();
  let main = document.querySelector('main') || document.body;
  if (main.innerText.trim().length < 600) main = document.body;
  const text = main.innerText.replace(/\\n{3,}/g,'\\n\\n').trim();
  const navText = clean((document.querySelector('header')||{}).innerText||'').slice(0,400);
  const seen = new Set(); const links = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const r = a.getBoundingClientRect(); if (!r.width && !r.height) return;
    const h = /#[/!]/.test(a.href) ? a.href : a.href.split('#')[0]; const t = clean(a.innerText || a.getAttribute('aria-label') || a.title).slice(0,70);
    if (!t || seen.has(h+t)) return; seen.add(h+t);
    links.push({t, h, zone: a.closest('header,nav')?'nav':(a.closest('footer')?'footer':'body')});
  });
  const buttons = [...document.querySelectorAll('button,[role=button],input[type=submit]')]
    .filter(b => b.getBoundingClientRect().width>0)
    .map(b => clean(b.innerText||b.value||b.getAttribute('aria-label'))).filter(Boolean).slice(0,30);
  const inputs = [...document.querySelectorAll('input:not([type=hidden]),textarea,select')]
    .filter(i => i.getBoundingClientRect().width>0)
    .map(i => ({type:i.type||i.tagName.toLowerCase(), name:i.name||i.id||'', ph:i.placeholder||'',
                label: clean((i.labels&&i.labels[0]&&i.labels[0].innerText)||i.getAttribute('aria-label')||'')})).slice(0,20);
  return {title: document.title, url: location.href, navText, text, links, buttons, inputs};
}"""

def open_ctx(p, user, st):
    prof = ROOT / "profiles" / RUN / user
    prof.mkdir(parents=True, exist_ok=True)
    kw = dict(headless=os.environ.get("SYNTH_HEADED") != "1")
    if st.get("device") == "mobile":
        dev = dict(p.devices["iPhone 14"]); dev.pop("default_browser_type", None)
        dev["user_agent"] = dev["user_agent"] + " " + UA_TAG
        kw.update(dev)
    else:
        kw.update(viewport={"width": 1440, "height": 900},
                  user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 " + UA_TAG))
    ctx = p.chromium.launch_persistent_context(str(prof), **kw)
    ctx.add_init_script(INIT_JS)
    return ctx

def render(user, st, view, perf, step, errors, offset=0):
    d = udir(user)
    (d / "pages" / f"{step:03d}.txt").write_text(view["url"] + "\n\n" + view["text"])
    body = view["text"][offset:offset + CHUNK]
    more = len(view["text"]) - (offset + CHUNK)
    out = [f"STEP {step} | {view['title']}", f"URL {view['url']}",
           f"PERF ttfb={perf['ttfb']}ms dcl={perf['dcl']}ms load={perf['load']}ms lcp={perf['lcp']}ms "
           f"cls={perf['cls']} {perf['kb']}KB {perf['requests']}req page_height={perf['height']}px"
           + (" HORIZONTAL-OVERFLOW" if perf['overflow'] else "")
           + (f" console_errors={len(errors)}" if errors else ""),
           f"SCREENSHOT {d / 'shots' / f'{step:03d}.jpg'}"]
    if offset == 0 and view.get("navText"):
        out.append(f"HEADER: {view['navText']}")
    out.append("--- PAGE TEXT" + (f" (chars {offset}-{offset+len(body)})" if offset else "") + " ---")
    out.append(body)
    if more > 0:
        out.append(f"... [{more} more chars — run `more`]")
    if offset == 0:
        body_links = [l for l in view["links"] if l["zone"] == "body"][:45]
        nav_links = [l for l in view["links"] if l["zone"] != "body"][:25]
        out.append("--- LINKS (body) ---")
        out += [f"- {l['t']} -> {l['h']}" for l in body_links]
        if nav_links and not st.get("nav_shown"):
            out.append("--- LINKS (header/footer, shown once) ---")
            out += [f"- {l['t']} -> {l['h']}" for l in nav_links]
            st["nav_shown"] = True
        if view["buttons"]:
            out.append("--- BUTTONS --- " + " | ".join(view["buttons"]))
        if view["inputs"]:
            out.append("--- INPUTS --- " + " | ".join(
                f"{i['type']}:{i['label'] or i['ph'] or i['name']}" for i in view["inputs"]))
    return "\n".join(out)

def visit(page, url):
    t0 = time.time()
    for attempt in (1, 2):
        try:
            page.goto(url, wait_until="load", timeout=40000)
            break
        except Exception as e:
            if attempt == 2:
                return False, str(e)[:200], round((time.time() - t0) * 1000)
    page.wait_for_timeout(1200)
    return True, "", round((time.time() - t0) * 1000)

def locate(page, target):
    for fn in (lambda: page.get_by_label(target, exact=False),
               lambda: page.get_by_placeholder(target, exact=False),
               lambda: page.get_by_role("button", name=target),
               lambda: page.get_by_role("link", name=target),
               lambda: page.get_by_text(target, exact=False),
               lambda: page.locator(target)):
        try:
            loc = fn()
            if loc.count() > 0:
                for i in range(min(loc.count(), 5)):
                    if loc.nth(i).is_visible():
                        return loc.nth(i)
        except Exception:
            continue
    return None

def main():
    user, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    st = load_state(user)
    if cmd == "init":
        st = {"device": args[args.index("--device") + 1] if "--device" in args else "desktop",
              "step": 0, "url": None, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if "--profile-from" in args:
            import shutil
            src = Path(args[args.index("--profile-from") + 1])
            if not src.is_absolute():
                src = ROOT / src
            dst = ROOT / "profiles" / RUN / user
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("Singleton*"))
        save_state(user, st)
        trace(user, {"event": "start", "device": st["device"]})
        print(f"init {user} device={st['device']}"); return
    if cmd == "end":
        trace(user, {"event": "end", "outcome": args[0], "note": " ".join(args[1:])})
        st["ended"] = args[0]; save_state(user, st); print("ended"); return
    if cmd == "more":
        if not st.get("step"):
            print("ERROR: no current page; use goto first"); return
        txt = (udir(user) / "pages" / f"{st['step']:03d}.txt").read_text().split("\n\n", 1)[1]
        off = st.get("offset", 0) + CHUNK; st["offset"] = off; save_state(user, st)
        print(txt[off:off + CHUNK] or "[end of page]")
        if len(txt) > off + CHUNK: print(f"... [{len(txt)-off-CHUNK} more chars]")
        trace(user, {"event": "more", "step": st["step"], "offset": off}); return

    with sync_playwright() as p:
        ctx = open_ctx(p, user, st)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text[:150]) if m.type == "error" else None)
        url = args[0] if cmd == "goto" else st.get("url")
        if not url:
            print("ERROR: no current page; use goto first"); return
        ok, err, wall = visit(page, url)
        if not ok:
            trace(user, {"event": "error", "cmd": cmd, "url": url, "error": err})
            print(f"ERROR loading {url}: {err}"); ctx.close(); return
        acted = []
        if cmd == "act":
            steps = json.loads(args[0])
            for s in steps:
                try:
                    if "wait" in s: page.wait_for_timeout(int(s["wait"])); acted.append(f"wait {s['wait']}")
                    elif "scroll" in s: page.mouse.wheel(0, int(s["scroll"])); page.wait_for_timeout(500); acted.append("scroll")
                    elif "press" in s: page.keyboard.press(s["press"]); page.wait_for_timeout(1500); acted.append(f"press {s['press']}")
                    else:
                        tgt = s.get("fill") or s.get("click") or s.get("select")
                        loc = locate(page, tgt)
                        if loc is None:
                            acted.append(f"NOT FOUND: {tgt}"); break
                        if "fill" in s: loc.fill(s["value"]); acted.append(f"filled {tgt}")
                        elif "select" in s: loc.select_option(label=s["value"]); acted.append(f"selected {tgt}")
                        else:
                            loc.click(timeout=8000); page.wait_for_timeout(2000); acted.append(f"clicked {tgt}")
                except Exception as e:
                    acted.append(f"FAILED {s}: {str(e)[:120]}"); break
            try: page.wait_for_load_state("load", timeout=10000)
            except Exception: pass
        perf = page.evaluate(PERF_JS)
        view = page.evaluate(VIEW_JS)
        st["step"] = st.get("step", 0) + 1; st["url"] = view["url"]; st["offset"] = 0
        step = st["step"]
        page.screenshot(path=str(udir(user) / "shots" / f"{step:03d}.jpg"), type="jpeg", quality=55,
                        full_page=(cmd == "shot" and "--full" in args))
        if acted: print("ACTIONS: " + "; ".join(acted))
        print(render(user, st, view, perf, step, errors))
        save_state(user, st)
        trace(user, {"event": cmd, "step": step, "url": view["url"], "title": view["title"],
                     "wall_ms": wall, "perf": perf, "actions": acted, "console_errors": errors[:5],
                     "text_hash": hashlib.md5(view["text"].encode()).hexdigest()[:10]})
        ctx.close()

if __name__ == "__main__":
    main()
