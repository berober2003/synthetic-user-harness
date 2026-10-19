# Synthetic User Harness

Persona-driven usability testing with AI agents and a real browser. You write a cast of fictional users, each with a job to do, a reason for showing up, a device, and a subject they know cold. One Claude agent plays each user. The agents browse your live site through a Playwright harness, leave an evidence trail at every step, and file a structured review at the end. A rollup and a digest turn a dozen reviews into one thing you can read in ten minutes.

It's built for the question a site owner can't answer from analytics: what does a specific kind of person think, step by step, when they land on this page with this problem?

## How it works

```
cast.json ──► one agent per user ──► browse.py (Playwright) ──► runs/<run>/<user>/
 personas       reads AGENT-BRIEF.md     persistent profile          trace.jsonl   append-only, every step
 users          browses in character     screenshots, page text      shots/*.jpg   viewport screenshots
 entry URLs     writes journal.md        Core Web Vitals per page    pages/*.txt   full page text
                writes review.json       console errors, overflow    review.json   structured verdict
                                                     │
                                aggregate.py ──► rollup.json   outcomes, paths, perf by page type
                                digest.py    ──► digest.md     one readable block per user
                                (optional)   ──► an HTML report you build from the two
```

**The cast.** A cast file holds a few personas (the archetypes: who they are, what job they're hiring the site for, their objections, what would convert them) and several users per persona (a name, a role, an age, a tech level, a device, an entry URL, the story of how they arrived, what they know cold, and a disposition). Three users per persona is a good default. Three people from the same segment take three different paths, and that spread is where the findings are.

**The harness.** `browse.py` is the only way an agent sees the site. Each command opens the user's own persistent Chromium profile, so cookies, local storage, usage meters and sign-in survive between steps the way they would for a real visitor. Every call prints what a person would take in (title, page text in chunks, links, buttons, form fields) plus a performance line (TTFB, LCP, CLS, page weight, request count, a horizontal-overflow flag on mobile). Every call also writes a screenshot, the full page text, and a line to `trace.jsonl`. Mobile users get a real iPhone 14 viewport and user agent. Each call relaunches the browser and reloads the user's current URL, so in-page state (an open dialog, a half-filled form) doesn't carry from one call to the next. A multi-step interaction goes in one `act` list. Profiles are kept per run (`profiles/<run>/<user>`), so a rerun of the same cast starts as a true first visit.

**The brief.** `briefs/AGENT-BRIEF.md` tells each agent how to behave: start at the entry URL, record the five-second impression before scrolling, browse the way the character would, leave when the character would leave, check the site's facts against what the character knows, and stay inside the hard limits. Agents append to a journal every three steps, so a stalled agent can be resumed without losing its run.

**The review.** Each agent ends by writing `review.json`: outcome, five-second impression, the journey with a sentiment score per step, ratings for the page elements it used, friction with severity and evidence, data issues with the exact text quoted, perceptions, feature use, felt performance, willingness to pay, quotes in character, and its top fixes.

**Returning users.** `briefs/RETURNING-USER.md` is a phase 2. The same user comes back a few days later, signed in to a free test account (set up once by hand with `login_once.py`), reads whatever emails phase 1 triggered, and reviews the signed-in experience: what changed, what's still gated, where the upgrade prompt lands, and whether this becomes a habit.

## Quick start

Requirements: Python 3.10+, Playwright with Chromium, and an agent runner that can execute shell commands (Claude Code is what this was built and run with).

```bash
pip install -r requirements.txt
```

```bash
python3 -m playwright install chromium
```

1. Write a cast. Start from `examples/cast.example.json`. Add `page_types` so the rollup groups pages the way you think about your site.
2. Fill in `briefs/AGENT-BRIEF.md` for your site: the features worth trying, what's allowed, the hard limits, and the element labels for ratings.
3. Smoke-test the harness yourself:

```bash
SYNTH_RUN=smoke python3 browse.py t1 init --device mobile
```

```bash
SYNTH_RUN=smoke python3 browse.py t1 goto https://example.com
```

4. Launch one agent per user, in parallel, each with the brief and its user id. In Claude Code that's one subagent per user. Sonnet carries the work well.
5. When the reviews are in, roll up and read:

```bash
python3 aggregate.py my-run --cast path/to/cast.json
```

```bash
python3 digest.py my-run --cast path/to/cast.json
```

6. Read `runs/my-run/digest.md` first, then go to screenshots and page text for anything you want to check.

To check the install, run the smoke test. It rebuilds a rollup and digest from a small committed fixture and exercises the harness without touching the network. Exit 0 means it works:

```bash
scripts/smoke.sh
```

Environment variables: `SYNTH_RUN` (run name), `SYNTH_HOME` (where `runs/` and `profiles/` live, default the repo; every run path in the briefs is relative to it, and the harness prints absolute paths), `SYNTH_UA_TAG` (User-Agent suffix, default `SyntheticUser/1.0 (origin=verification)`), `SYNTH_CHUNK` (characters of page text per chunk), `SYNTH_HEADED=1` to watch the browser.

## Use cases

- Pre-launch review of a site or a redesign by the people it's for, before real traffic sees it
- Data QA on catalog, directory, marketplace and comparison sites, using personas who know a category cold (wrong categories, stale facts, counts that disagree, missing obvious entries, bad names)
- Pricing and paywall pages: where the gate lands, what each segment expects to see before paying, what price reaction you get
- Onboarding and sign-up flows up to the button, then the signed-in experience in phase 2
- Newsletter and transactional email flows: did the email arrive, what did it say, did it bring the user back
- Ecommerce: product pages, search, filters, size guides, cart, and checkout up to the payment step
- Mobile vs desktop: layout overflow, tap targets for a low-tech persona, LCP by page type and device
- Five-second tests on homepage and landing page copy, by segment
- Developer docs and portals: can a developer persona find the API key, the quickstart, the rate limits
- Regression after fixes ship: rerun the same cast and compare rollups, run against run
- Competitor walkthroughs on public pages, to see your category through a buyer's eyes
- Feeding coding agents: each finding carries a URL and quoted evidence, so it can become a scoped fix, then a rerun checks whether it held

## What it can't do

These are AI agents playing people. The findings are hypotheses with evidence attached, not user research results.

- **Ratings flatten.** Model-judged trust and clarity scores bunch up in the middle of the scale. Weight the evidence-backed findings (data issues, broken features, quoted copy) over the numbers.
- **Feelings are simulated.** An agent's "I'd leave here" is a prediction. Check the important ones against real sessions, real conversion data, or real interviews before acting on them.
- **SSO blocks automation.** Google and most identity providers reject sign-in from automated browsers. Phase 2 needs an email-link or password test account, signed in once by hand.
- **Long parallel runs stall.** Agents running in parallel can all stall at once on an upstream timeout. The journal-every-3-steps rule makes resuming lossless. Keep it.
- **It costs tokens.** A 12-user run is a few hundred harness calls and a lot of page text. The chunked page text and the call budget in the brief keep it in bounds.

## Safety and test hygiene

- Hard limits live in the brief and the agents follow them: no account creation, no checkout, no payment details, no sign-in-link buttons unless you explicitly allow it for your own site.
- Every request carries the `SYNTH_UA_TAG` User-Agent suffix so you can filter synthetic traffic out of analytics.
- Every trace line is stamped `origin: verification` so test runs never mix with production numbers.
- Use plus-addressed or test-domain emails for anything the agents submit, and purge those test records from your email platform and database afterwards.
- Only point this at sites you own or have permission to test. Keep agent traffic polite: the harness runs one page at a time per user.

## Files

| File | What it does |
|---|---|
| `browse.py` | The browser harness. `init`, `goto`, `more`, `act`, `shot`, `end` |
| `aggregate.py` | Traces and reviews into `rollup.json`: outcomes, paths, performance by page type, overflow and console-error pages |
| `digest.py` | Reviews into `digest.md`, one readable block per user |
| `login_once.py` | Opens a headed browser so you can sign in once; phase 2 users clone that profile |
| `briefs/AGENT-BRIEF.md` | Template brief for phase 1 |
| `briefs/RETURNING-USER.md` | Template brief for the signed-in, returning-user phase |
| `examples/cast.example.json` | An example cast for a fictional meal-kit site: two personas, four users |
| `examples/fixture/` | A two-user fake run used by the smoke test |
| `scripts/smoke.sh` | The done-condition check: fixture rollup, digest and harness, exit 0 on success |
| `LICENSE` | MIT |

`runs/` and `profiles/` are created on first use and ignored by git. Profiles hold cookies and sessions; never commit them. `login_once.py` writes the shared signed-in profile to `profiles/_authed`; phase 2 users clone it per run.

## Where this is going

Plenty of tools can run synthetic users now. The harder question is how far to trust what they report. The next step is calibration: run a cast against a site that has real session data and real conversion numbers, measure where the synthetic findings agree with real users and where they produce false positives, and show that agreement rate next to each kind of finding.

---

## Changelog

- 2026-10-19: Published. MIT license added.
- 2026-10-19: Extracted into its own repo. Harness made site-agnostic (`SYNTH_HOME`, `SYNTH_UA_TAG`, `SYNTH_RUN` defaults), page types moved into the cast, `digest.py` added, `login_once.py` takes a URL and marker, generic phase 1 and phase 2 brief templates added. Profiles moved under the run name so reruns start clean; `--profile-from` resolves against `SYNTH_HOME`; screenshot paths print absolute; `more` before `goto` errors cleanly. Added a fixture run and `scripts/smoke.sh`. Verified end to end: rollup and digest rebuilt from real run data, a live mobile run on example.com, and the smoke test.
