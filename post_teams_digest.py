#!/usr/bin/env python3
"""Post the Endpoint Release Watch daily digest to a Teams channel.

Reads digest.json (written by the scheduled task) and posts an Adaptive Card
to the Teams Workflows webhook URL from the TEAMS_WEBHOOK_URL environment
variable, or from teams_webhook.txt when that variable isn't set.

Usage:
  python3 post_teams_digest.py            post digest.json
  python3 post_teams_digest.py --dry-run  print the card JSON instead of posting
  python3 post_teams_digest.py --test     post a short test card

digest.json shape:
  {"date": "YYYY-MM-DD",
   "added": [row, ...],          # rows added this run (tracker row fields)
   "deadlines": [row, ...]}      # rows with a deadline in the next 30 days
"""
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
TRACKER = "https://claude.ai/artifact/Q5R6nnLxW8wX374qE7cD2M"
TAB_ORDER = ["Windows", "Intune", "Apple", "Microsoft 365", "Copilot", "SharePoint", "Teams", "Exchange"]


def text(t, **kw):
    return {"type": "TextBlock", "text": t, "wrap": True, **kw}


AP_MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def fmt(d, year=False):
    """AP-style date, like Sept. 23 or March 4, 2027."""
    if not d:
        return ""
    x = date.fromisoformat(d)
    return f"{AP_MONTHS[x.month - 1]} {x.day}" + (f", {x.year}" if year else "")


def item_line(r, with_action=False):
    line = f"**{r['platform']}** · [{r['title']}]({r['url']})"
    if with_action and r.get("action"):
        line += f"  \n{r['action']}"
    return line


def build_card(d):
    added = d.get("added", [])
    action = [r for r in added if r.get("impact") == "action"]
    emerging = [r for r in added if r.get("lane") == "emerging" and r.get("impact") != "action"]
    other = [r for r in added if r not in action and r not in emerging]
    deadlines = sorted(d.get("deadlines", []), key=lambda r: r["deadline"])

    n = len(added)
    head = f"{n} new update{'s' if n != 1 else ''}"
    if action:
        head += f" · {len(action)} need{'s' if len(action) == 1 else ''} action"

    body = [
        text("Endpoint Release Watch", weight="Bolder", size="Large"),
        text(f"{date.fromisoformat(d['date']).strftime('%A')}, {fmt(d['date'], year=True)} · {head}",
             isSubtle=True, spacing="None"),
    ]

    def section(title, rows, color=None, with_action=False, limit=8):
        if not rows:
            return
        body.append(text(title, weight="Bolder", spacing="Medium", **({"color": color} if color else {})))
        for r in rows[:limit]:
            body.append(text("- " + item_line(r, with_action), spacing="Small"))
        if len(rows) > limit:
            body.append(text(f"And {len(rows) - limit} more in the tracker", isSubtle=True, spacing="Small"))

    section("Action Needed", action, color="Attention", with_action=True)
    section("New and Emerging", emerging, color="Accent", limit=5)
    if other:
        by = {}
        for r in other:
            by.setdefault(r["platform"], []).append(r)
        body.append(text("Other Updates", weight="Bolder", spacing="Medium"))
        for tab in TAB_ORDER:
            if tab in by:
                titles = "; ".join(r["title"] for r in by[tab][:3])
                more = f" (+{len(by[tab]) - 3} more)" if len(by[tab]) > 3 else ""
                body.append(text(f"**{tab}** ({len(by[tab])}): {titles}{more}", spacing="Small"))
    if deadlines:
        body.append(text("Coming Up in the Next 30 Days", weight="Bolder", spacing="Medium"))
        for r in deadlines[:6]:
            body.append(text(f"- **{fmt(r['deadline'])}** · {r['platform']} · {r['title']}", spacing="Small"))

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
        "actions": [{"type": "Action.OpenUrl", "title": "Open tracker", "url": TRACKER}],
    }


def webhook_url():
    """TEAMS_WEBHOOK_URL (cloud routine) wins; teams_webhook.txt is the local fallback."""
    url = os.environ.get("TEAMS_WEBHOOK_URL", "").strip()
    url_file = HERE / "teams_webhook.txt"
    if not url and url_file.exists():
        url = url_file.read_text().strip()
    if not url:
        sys.exit(f"No webhook URL. Set TEAMS_WEBHOOK_URL or paste the Teams Workflows URL into {url_file}")
    return url


def post(card):
    url = webhook_url()
    payload = {"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print("Posted to Teams:", r.status)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        card = {"type": "AdaptiveCard", "version": "1.4", "body": [
            text("Endpoint Release Watch", weight="Bolder", size="Large"),
            text("Test post. Daily digests will appear here on weekday mornings when there are new updates.")],
            "actions": [{"type": "Action.OpenUrl", "title": "Open tracker", "url": TRACKER}]}
        post(card)
        sys.exit()
    d = json.loads((HERE / "digest.json").read_text())
    if not d.get("added"):
        print("Nothing new; skipping the Teams post.")
        sys.exit()
    card = build_card(d)
    if "--dry-run" in args:
        print(json.dumps(card, indent=1))
    else:
        post(card)
