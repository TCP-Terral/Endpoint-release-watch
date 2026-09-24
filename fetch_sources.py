#!/usr/bin/env python3
"""Pull recent release items from Microsoft and Apple sources into candidates.json.

Usage: python3 fetch_sources.py [days_back]   (default 14)

Output is raw candidates only. Deciding what's significant happens afterward.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 14
CUTOFF = datetime.now(timezone.utc) - timedelta(days=DAYS)
OUT = Path(__file__).with_name("candidates.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept": "application/rss+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.5", "Accept-Language": "en-US"}

# M365 roadmap products worth tracking (Copilot Studio, Planner and OneNote included) for endpoint and tenant admins
M365_PRODUCTS = [
    "Microsoft Intune", "Microsoft Entra", "Microsoft Defender", "Microsoft Purview",
    "Exchange", "Outlook", "Microsoft Teams", "SharePoint", "OneDrive", "Windows",
    "Microsoft 365 admin center", "Microsoft 365 app", "Microsoft 365 Apps",
    "Microsoft Copilot", "Copilot Studio", "Microsoft Edge", "Windows 365", "Planner", "OneNote",
]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")


def clean(s, n=600):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return s[:n]


def page_text(raw):
    m = re.search(r"<main.*?</main>", raw, re.S)
    s = m.group(0) if m else raw
    s = re.sub(r"<(script|style).*?</\1>", "", s, flags=re.S)
    s = re.sub(r"<h([1-4])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", s)
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"<(p|br|tr)[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n\s*\n+", "\n", s)


def rss(url, source, platform, keep=lambda cats, title: True, lane="change"):
    out = []
    root = ET.fromstring(get(url))
    for it in root.iter("item"):
        try:
            d = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        if d < CUTOFF:
            continue
        cats = [c.text or "" for c in it.findall("category")]
        title = it.findtext("title") or ""
        if not keep(cats, title):
            continue
        out.append({
            "source": source, "platform": m365_tab(title) if platform == "M365_AUTO" else platform,
            "title": title.strip(),
            "url": (it.findtext("link") or "").strip(), "date": d.date().isoformat(),
            "tags": cats[:8], "text": clean(it.findtext("description")), "lane_hint": lane,
        })
    # Atom feeds (Apple Newsroom)
    A = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(A + "entry"):
        try:
            d = datetime.fromisoformat((it.findtext(A + "updated") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if d < CUTOFF:
            continue
        cats = [c.get("term", "") for c in it.findall(A + "category")]
        title = (it.findtext(A + "title") or "").strip()
        if not keep(cats, title):
            continue
        link = next((l.get("href") for l in it.findall(A + "link") if l.get("rel") in (None, "alternate")), "")
        out.append({
            "source": source, "platform": platform, "title": title, "url": link,
            "date": d.date().isoformat(), "tags": cats[:8],
            "text": clean(it.findtext(A + "content") or it.findtext(A + "summary")), "lane_hint": lane,
        })
    return out


def m365_tab(title):
    """Map an M365 roadmap title to its tracker tab."""
    t = title.lower()
    if "copilot" in t.split(":")[0] or "copilot studio" in t:
        return "Copilot"
    for key, tab in (("microsoft teams", "Teams"), ("sharepoint", "SharePoint"), ("onedrive", "SharePoint"),
                     ("outlook", "Exchange"), ("exchange", "Exchange")):
        if t.startswith(key):
            return tab
    return "Microsoft 365"


def m365_keep(cats, title):
    return any(p.lower() in (title + " " + " ".join(cats)).lower() for p in M365_PRODUCTS)


def intune_whats_new():
    url = "https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/whats-new"
    t = page_text(get(url))
    out = []
    for week in re.split(r"\n## (?=Week of )", t)[1:]:
        head, _, body = week.partition("\n")
        m = re.match(r"Week of (\w+ \d+, \d{4})", head)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc)
        if d < CUTOFF:
            break
        for feat in re.split(r"\n#### ", body)[1:]:
            ftitle, _, ftext = feat.partition("\n")
            out.append({
                "source": "Intune What's New", "platform": "Intune", "title": ftitle.strip(),
                "url": url, "date": d.date().isoformat(), "tags": [head.strip()],
                "text": clean(ftext, 800),
            })
    return out


def windows_message_center():
    url = "https://learn.microsoft.com/en-us/windows/release-health/windows-message-center"
    t = page_text(get(url))
    t = t.split("## Recent announcements", 1)[-1].split("\n## ", 1)[0]
    out = []
    # Each message ends with a date stamp like 2026-09-22 \n10:00 PT
    parts = re.split(r"(\d{4}-\d{2}-\d{2})\s*\n\s*\d{1,2}:\d{2} PT", t)
    for i in range(0, len(parts) - 1, 2):
        body, date = parts[i].strip(), parts[i + 1]
        d = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        if d < CUTOFF:
            continue
        lines = [l for l in body.split("\n") if l.strip() and l.strip() != "MessageDate"]
        if not lines:
            continue
        out.append({
            "source": "Windows message center", "platform": "Windows", "title": lines[0].strip(),
            "url": url, "date": date, "tags": [], "text": clean(" ".join(lines[1:]), 900),
        })
    return out


def apple_security():
    url = "https://support.apple.com/en-us/100100"
    raw = get(url)
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", raw, re.S):
        cells = [clean(c, 300) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        link = re.search(r'href="([^"]+)"', row)
        if len(cells) < 3:
            continue
        try:
            d = datetime.strptime(cells[2], "%d %b %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if d < CUTOFF:
            continue
        href = link.group(1) if link else url
        if href.startswith("/"):
            href = "https://support.apple.com" + href
        out.append({
            "source": "Apple security releases", "platform": "Apple", "title": cells[0],
            "url": href, "date": d.date().isoformat(), "tags": [cells[1]], "text": cells[0],
        })
    return out


SOURCES = [
    lambda: rss("https://www.microsoft.com/releasecommunications/api/v2/m365/rss",
                "Microsoft 365 Roadmap", "M365_AUTO", m365_keep),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=Exchange",
                "Exchange Team Blog", "Exchange"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=SPBlog",
                "SharePoint Blog", "SharePoint"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=MicrosoftTeamsBlog",
                "Microsoft Teams Blog", "Teams"),
    lambda: rss("https://www.microsoft.com/en-us/microsoft-copilot/blog/copilot-studio/feed/",
                "Copilot Studio Blog", "Copilot", lane="emerging"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=Windows-ITPro-blog",
                "Windows IT Pro Blog", "Windows"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=IntuneCustomerSuccess",
                "Intune Customer Success Blog", "Intune"),
    lambda: rss("https://developer.apple.com/news/releases/rss/releases.rss",
                "Apple Developer Releases", "Apple",
                lambda c, t: bool(re.match(r"(macOS|iOS|iPadOS)\b", t)), lane="emerging"),
    # New releases and emerging tech
    lambda: rss("https://blogs.windows.com/windows-insider/feed/",
                "Windows Insider Blog", "Windows", lane="emerging"),
    lambda: rss("https://blogs.windows.com/windowsexperience/feed/",
                "Windows Experience Blog", "Windows", lane="emerging"),
    lambda: rss("https://www.microsoft.com/en-us/microsoft-365/blog/feed/",
                "Microsoft 365 Blog", "Microsoft 365", lane="emerging"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=Microsoft365InsiderBlog",
                "Microsoft 365 Insider Blog", "Microsoft 365", lane="emerging"),
    lambda: rss("https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=microsoft-entra-blog",
                "Microsoft Entra Blog", "Microsoft 365", lane="emerging"),
    lambda: rss("https://blogs.microsoft.com/feed/",
                "Official Microsoft Blog", "Microsoft 365", lane="emerging"),
    lambda: rss("https://www.apple.com/newsroom/rss-feed.rss",
                "Apple Newsroom", "Apple", lane="emerging"),
    intune_whats_new,
    windows_message_center,
    apple_security,
]

if __name__ == "__main__":
    items, errors = [], []
    for fn in SOURCES:
        try:
            items += fn()
        except Exception as e:  # keep going if one source breaks
            errors.append(repr(e))
    OUT.write_text(json.dumps({"fetched": datetime.now(timezone.utc).isoformat(),
                               "days": DAYS, "errors": errors, "items": items}, indent=1))
    by = {}
    for i in items:
        by[i["source"]] = by.get(i["source"], 0) + 1
    print(f"{len(items)} candidates -> {OUT}")
    for k, v in by.items():
        print(f"  {v:4}  {k}")
    for e in errors:
        print("  ERROR", e)
