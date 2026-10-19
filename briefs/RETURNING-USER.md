# Returning User Brief (template)

Phase 2 of a run. Read `AGENT-BRIEF.md` first: its harness, hard limits, save-as-you-go and budget rules all still apply. This addendum changes four things.

Paths under `runs/` and `profiles/` are relative to `$SYNTH_HOME` (the repo root unless it's set).

1. **Time skip:** it is now {{DAYS}} days after your first visit. Your first-visit notes are in `runs/{{RUN}}/<id>/journal.md` and `review.json`. Read them first. You come back with the same need, plus whatever stuck with you.
2. **You are signed in** to a free test account. Your harness id for this phase is `<id>-r`. Initialize it with:
   `python3 browse.py <id>-r init --device <your device> --profile-from profiles/_authed`
   (The `_authed` profile comes from `login_once.py`.) The account is shared test infrastructure. Do not change settings, delete anything, start a checkout, enter payment details, or sign out.
3. **Inbox:** if `runs/{{RUN}}/inbox/<id>.md` exists, it holds the emails your phase 1 actions triggered. Read them in character before you browse. If you subscribed or signed up in phase 1 and the file doesn't exist, no email arrived. Record that as a finding.
4. **What to evaluate:** the signed-in, returning experience. What changed now that you're signed in: the account page, any meter or usage counter, what's unlocked and what's still gated, upgrade prompts, whether the site remembers you. Re-check the thing you care about. Decide whether this becomes a habit or a one-time visit.

Budget: 12 to 20 harness calls.

**Output:** write `runs/{{RUN}}/<id>-r/review.json` with the phase 1 schema, plus:

```json
"returning": {
  "what_changed_when_signed_in": "",
  "meter_or_limits_seen": "",
  "email_reaction": "",
  "habit_potential_1to5": 3,
  "upgrade_trigger": "the exact moment that would make you pay, or why it never comes",
  "churn_risk": "why you would never come back"
}
```

Return only 3 lines, as in phase 1.
