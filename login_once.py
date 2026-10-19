#!/usr/bin/env python3
"""Sign in once by hand, then let synthetic users reuse the session.

Opens a headed browser on the login URL with a dedicated profile
(profiles/_authed). You sign in with a FREE test account. The script polls the
page until the signed-in marker text appears, then closes. Signed-in users
clone that profile with:
    browse.py <user> init --device desktop --profile-from profiles/_authed

Usage: login_once.py <login-url> [--marker "sign out"] [--minutes 120]

Google and most SSO providers reject sign-in from automated browsers. Use an
email-link or password test account, never a real personal login.
"""
import argparse, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("--marker", action="append", help="text that only shows when signed in (repeatable)")
ap.add_argument("--minutes", type=int, default=120)
a = ap.parse_args()
markers = [m.lower() for m in (a.marker or ["sign out", "log out"])]
root = Path(os.environ.get("SYNTH_HOME") or Path(__file__).resolve().parent)
prof = root / "profiles" / "_authed"
prof.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(str(prof), headless=False, viewport={"width": 1280, "height": 860})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(a.url)
    deadline = time.time() + a.minutes * 60
    while time.time() < deadline:
        time.sleep(10)
        try:
            txt = page.evaluate("document.body.innerText").lower()
            if any(m in txt for m in markers):
                print("AUTHED at", page.url); time.sleep(5); break
        except Exception:
            pass
    else:
        print("timed out without seeing a signed-in marker")
    ctx.close()
