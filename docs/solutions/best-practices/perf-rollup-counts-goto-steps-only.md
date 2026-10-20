---
title: Performance rollup counts goto steps only
date: 2026-10-20
category: best-practices
module: aggregate.py perf rollup
problem_type: best_practice
component: observability
severity: medium
applies_when:
  - Changing which trace events feed perf_by_page_type in aggregate.py
  - Testing a single-page app, where clicks change the route without a new document load
related_components:
  - browse.py
tags: [performance, core-web-vitals, spa, rollup, page-types]
---

# Performance rollup counts goto steps only

## Context

`aggregate.py` builds `perf_by_page_type` (median LCP, TTFB and page weight per page type) from the trace. Every `goto`, `act` and `shot` step records a `perf` object, but only `goto` steps feed the rollup (`aggregate.py`, the `if s["event"] == "goto":` line). Adding `act` steps looks like a free way to get more samples. It was tried and reverted, because on single-page apps it attributes timings to the wrong page.

## Guidance

Keep the perf rollup to `goto` steps. Don't add `act` steps unless each sample can be proven to describe the page it is credited to.

The mismatch comes from how `browse.py` measures:

- `PERF_JS` reads `performance.getEntriesByType('navigation')[0]` and the LCP value collected by a `PerformanceObserver`. Both describe the document the browser actually loaded.
- Each `act` call relaunches the browser, reloads the user's saved URL, then runs the steps. So the navigation entry belongs to the page before the click.
- After the steps, the trace records `view["url"]`, the location at the end. On a single-page app a click changes that location client-side, with no new navigation entry.

So an `act` sample on an SPA pairs the starting document's TTFB and LCP with the destination route's URL, and `page_type()` credits them to the destination's page type.

If act-step perf is ever needed, a safe version records the document URL with the measurement (for example `doc: n.name` in `PERF_JS`) and counts an act sample only when that URL matches the step's URL, ignoring the fragment. Traces without the field are skipped.

## Why This Matters

The skew is silent. On a multi-page site a click triggers a full navigation, so the numbers come out right and a test run looks fine. On an SPA the per-page-type medians blend the landing document's load into every route clicked to, so a slow landing page shows up as a slow checkout, and a fast route hides behind the landing page's numbers.

## When to Apply

- Any change to the event filter in the perf loop of `aggregate.py`
- Any new metric read from `performance` entries in `browse.py`

## Examples

Before (reverted), every navigation-like step fed the rollup:

```python
if s["event"] in ("goto", "act"):
    perf[page_type(s["url"])].append(...)
```

After (current), only steps that loaded the page they are credited to:

```python
if s["event"] == "goto":
    perf[page_type(s["url"])].append(...)
```

## Related

- `browse.py` docstring: each command relaunches the browser and reloads the current URL.
