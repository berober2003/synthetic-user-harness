#!/usr/bin/env python3
"""Flatten every review.json in a run into one plain-text digest.

The digest is what a person (or a synthesis agent) reads first: one block per
synthetic user with the outcome, first impression, friction, data issues,
quotes and top fixes. Output: runs/<run>/digest.md

Usage: digest.py <run> --cast <cast.json>
"""
import argparse, json, os
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--cast", required=True)
a = ap.parse_args()

ROOT = Path(os.environ.get("SYNTH_HOME") or Path(__file__).resolve().parent)
rd = ROOT / "runs" / a.run
cast = {u["id"]: u for u in json.load(open(a.cast))["users"]}

out = [f"# Digest: {a.run}", ""]
for f in sorted(rd.glob("*/review.json")):
    uid = f.parent.name
    try:
        r = json.load(open(f))
    except Exception as e:
        out += [f"## {uid} | review.json did not parse: {e}", ""]; continue
    u = cast.get(uid.removesuffix("-r"), {})
    fi = r.get("first_impression", {})
    eng = r.get("engagement", {})
    out.append(f"## {uid} {u.get('name', r.get('name', ''))} | {r.get('outcome', '?')} | "
               f"{u.get('device', r.get('device', ''))} | entry {u.get('entry', r.get('entry_url', ''))}")
    out.append(f"SUMMARY: {r.get('summary', '')}")
    out.append(f"5S: {fi.get('five_seconds', '')} | understood product: {fi.get('understood_product')} "
               f"| trust {fi.get('trust_1to5')} clarity {fi.get('clarity_1to5')}")
    j = r.get("journey", [])
    if j:
        out.append("JOURNEY: " + " > ".join(f"{s.get('url', '')}({s.get('sentiment', 0)})" for s in j))
    for x in r.get("friction", []):
        out.append(f"FRICTION[{x.get('severity')}] {x.get('url', '')}: {x.get('what', '')}")
    for x in r.get("data_issues", []):
        out.append(f"DATA[{x.get('confidence')}] {x.get('url', '')}: {x.get('issue', '')} :: {x.get('evidence', '')}")
    out.append(f"ENGAGEMENT: would_pay={eng.get('would_pay')} recommend={eng.get('recommend_0to10')} "
               f"back={eng.get('what_brings_me_back', '')}")
    for q in r.get("quotes", []):
        out.append(f"QUOTE: {q}")
    if r.get("awesome"):
        out.append(f"AWESOME: {r['awesome']}")
    for x in r.get("top_fixes", []):
        out.append(f"FIX[{x.get('impact')}]: {x.get('fix', '')}")
    if r.get("returning"):
        out.append("RETURNING: " + json.dumps(r["returning"]))
    out.append("")

(rd / "digest.md").write_text("\n".join(out))
print(f"wrote {rd / 'digest.md'} ({len(list(rd.glob('*/review.json')))} reviews)")
