#!/usr/bin/env python3
"""Roll up a run: per-user traces + reviews -> runs/<run>/rollup.json.

Compact by design: the synthesis step reads this one file, not a dozen raw
agent transcripts.

Usage: aggregate.py <run> --cast <cast.json>

Page types come from the cast's optional "page_types" list. Each entry is
[path_prefix, label], or [path, label, "exact"] for a page that only matches
its own path (a directory index, say). Exact entries are checked first, then
prefixes in order, so put longer prefixes first. Unmatched pages are labelled
by their first path segment.
"""
import argparse, json, os, statistics as st
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--cast", required=True)
a = ap.parse_args()

ROOT = Path(os.environ.get("SYNTH_HOME") or Path(__file__).resolve().parent)
rd = ROOT / "runs" / a.run
cast_doc = json.load(open(a.cast))
cast = {u["id"]: u for u in cast_doc["users"]}
PAGE_TYPES = cast_doc.get("page_types", [])

def page_type(url):
    p = urlparse(url).path or "/"
    if p == "/":
        return "Homepage"
    for path, label, *mode in PAGE_TYPES:
        if mode == ["exact"] and p.rstrip("/") == path.rstrip("/"):
            return label
    for path, label, *mode in PAGE_TYPES:
        if not mode and (p.rstrip("/") == path.rstrip("/") or p.startswith(path.rstrip("/") + "/")):
            return label
    return p.strip("/").split("/")[0]

def base_id(name):
    # returning-user phases run as "<id>-r"
    return name[:-2] if name.endswith("-r") else name

perf = defaultdict(list); users = {}; overflow = set(); errors = defaultdict(int)
for ud in sorted(rd.iterdir()):
    if not ud.is_dir() or base_id(ud.name) not in cast: continue
    who = cast[base_id(ud.name)]
    steps = [json.loads(l) for l in open(ud / "trace.jsonl")] if (ud / "trace.jsonl").exists() else []
    nav = [s for s in steps if s.get("event") in ("goto", "act", "shot") and s.get("perf")]
    for s in nav:
        if s["event"] == "goto":
            perf[page_type(s["url"])].append({"lcp": s["perf"]["lcp"], "ttfb": s["perf"]["ttfb"], "kb": s["perf"]["kb"],
                                              "device": who["device"], "url": s["url"]})
        if s["perf"].get("overflow"): overflow.add(s["url"])
        if s.get("console_errors"): errors[s["url"]] += len(s["console_errors"])
    end = next((s for s in steps if s.get("event") == "end"), {})
    rev = None
    if (ud / "review.json").exists():
        try: rev = json.load(open(ud / "review.json"))
        except Exception as e: rev = {"_error": str(e)}
    users[ud.name] = {"steps": len(nav), "outcome_trace": end.get("outcome", "no-end-record"),
                      "path": [page_type(s["url"]) + " " + urlparse(s["url"]).path for s in nav],
                      "review": rev}

perf_summary = {}
for pt, rows in perf.items():
    lcps = [r["lcp"] for r in rows if r["lcp"]]; ttfbs = [r["ttfb"] for r in rows]
    perf_summary[pt] = {"n": len(rows), "lcp_median": int(st.median(lcps)) if lcps else None,
                        "lcp_max": max(lcps) if lcps else None, "ttfb_median": int(st.median(ttfbs)) if ttfbs else None,
                        "kb_median": int(st.median([r["kb"] for r in rows])),
                        "worst": max(rows, key=lambda r: r["lcp"] or 0)["url"]}
out = {"run": a.run, "users": users, "perf_by_page_type": perf_summary,
       "overflow_urls": sorted(overflow), "console_error_urls": dict(errors)}
(rd / "rollup.json").write_text(json.dumps(out, indent=1))
print(f"users={len(users)} reviews={sum(1 for u in users.values() if u['review'])} page_types={len(perf_summary)}")
for pt, s in sorted(perf_summary.items(), key=lambda x: -(x[1]['lcp_median'] or 0)):
    print(f"{pt:18} n={s['n']:3} lcp_med={s['lcp_median']} ttfb_med={s['ttfb_median']} kb={s['kb_median']}")
print("overflow:", len(overflow), "console-error pages:", len(errors))
