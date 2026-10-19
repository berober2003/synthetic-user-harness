#!/usr/bin/env bash
# Done-condition check. Exit 0 means the harness, rollup and digest all work.
# Runs aggregate.py and digest.py on the committed fixture, then a browse.py
# init/more-guard/end pair (no network) under a throwaway SYNTH_HOME.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'find "$TMP" -delete' EXIT
export SYNTH_HOME="$TMP"
mkdir -p "$TMP/runs" && cp -R "$REPO/examples/fixture/run" "$TMP/runs/fixture"
CAST="$REPO/examples/fixture/cast.json"

# The example cast the README points to must parse and have the fields the tools read.
python3 - "$REPO/examples/cast.example.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
assert c["users"] and all({"id", "persona", "device", "entry"} <= set(u) for u in c["users"])
assert all(u["persona"] in c["personas"] for u in c["users"])
PY

python3 "$REPO/aggregate.py" fixture --cast "$CAST"
python3 - "$TMP/runs/fixture/rollup.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert set(r["users"]) == {"u1", "u1-r", "u2"}, r["users"].keys()
assert set(r["perf_by_page_type"]) == {"Homepage", "Pricing", "Docs index", "Docs page"}, r["perf_by_page_type"].keys()
assert r["users"]["u2"]["review"].get("_error"), "bad review.json should be flagged"
assert r["console_error_urls"] == {"https://example.com/pricing/": 2}, r["console_error_urls"]
PY

python3 "$REPO/digest.py" fixture --cast "$CAST"
D="$TMP/runs/fixture/digest.md"
grep -q "## u1 Fixture One | converted" "$D"
grep -q "DATA\[high\] /pricing/: Fixture issue :: exact text" "$D"
grep -q "RETURNING:" "$D"
grep -q "## u2 | review.json did not parse" "$D"

export SYNTH_RUN=smoke
python3 "$REPO/browse.py" s1 init --device mobile
python3 "$REPO/browse.py" s1 more | grep -q "no current page"
python3 "$REPO/browse.py" s1 end clean "smoke"
grep -q '"outcome": "clean"' "$TMP/runs/smoke/s1/trace.jsonl"
mkdir -p "$TMP/profiles/_authed" && touch "$TMP/profiles/_authed/marker"
(cd / && python3 "$REPO/browse.py" s1-r init --device desktop --profile-from profiles/_authed)
test -f "$TMP/profiles/smoke/s1-r/marker"

echo "SMOKE OK"
