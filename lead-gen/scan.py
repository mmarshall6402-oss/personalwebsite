"""
Scan Google Maps (by driving headless Chromium) for businesses with no
website listed, sorted by review count (most-reviewed first). Writes
output/prospects.csv.

Note: this scrapes Google Maps directly rather than using the Places API,
which is against Google's Terms of Service and inherently fragile -- Maps'
HTML structure changes without notice, so the selectors below may need
updates over time. MAX_RESULTS_PER_QUERY and the *_DELAY_RANGE constants
are the knobs to loosen (faster) or tighten (safer) if runs are getting
blocked or are too slow.

Setup:
    pip install -r requirements.txt
    playwright install chromium
    cp .env.example .env   # optional: fill in GOOGLE_CSE_ID/GOOGLE_CSE_KEY

Usage:
    Edit QUERIES below, then:
    python scan.py
"""

import csv
import glob
import hashlib
import os
import random
import re
import time
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

load_dotenv()

# --- Edit these for whatever neighborhoods/niches you're prospecting -------
QUERIES = [
    "plumbers in Houston TX 77025",
    "hair salons in Houston TX 77025",
    "auto repair shops in Houston TX 77025",
    "landscaping lawn care in Houston TX 77025",
]
# ----------------------------------------------------------------------------

GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MAX_RESULTS_PER_QUERY = 30
MAX_SCROLL_ATTEMPTS_WITHOUT_NEW = 3
SCROLL_DELAY_RANGE = (1.0, 2.5)
CARD_DELAY_RANGE = (1.5, 3.5)
QUERY_DELAY_RANGE = (4.0, 9.0)

# Domains that show up in search results but aren't a business's own site.
DIRECTORY_DOMAINS = {
    "facebook.com", "instagram.com", "yelp.com", "yellowpages.com",
    "mapquest.com", "google.com", "goo.gl", "maps.google.com",
    "foursquare.com", "tripadvisor.com", "linkedin.com", "twitter.com",
    "x.com", "nextdoor.com", "bbb.org", "angi.com", "thumbtack.com",
    "indeed.com", "glassdoor.com", "opentable.com", "grubhub.com",
    "doordash.com", "ubereats.com", "zomato.com", "youtube.com",
    "pinterest.com", "tiktok.com",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def human_delay(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def find_prebuilt_chromium() -> str | None:
    """Locate a pre-provisioned Chromium build if one is set up on this
    machine (e.g. a sandboxed dev environment), so Playwright doesn't need
    its own browser install here. Returns None if none is found, in which
    case Playwright falls back to its normal resolution -- the standard
    path once you've run `playwright install chromium` yourself."""
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not browsers_path:
        return None
    matches = glob.glob(os.path.join(browsers_path, "chromium-*", "chrome-linux", "chrome"))
    return matches[0] if matches else None


def accept_consent(page) -> None:
    """Best-effort dismissal of Google's cookie-consent interstitial."""
    try:
        btn = page.get_by_role("button", name=re.compile(r"Accept all|I agree", re.IGNORECASE))
        if btn.count() > 0:
            btn.first.click(timeout=3000)
            human_delay(1, 2)
    except Exception:
        pass


def collect_listing_urls(page, query: str) -> list[str]:
    """Search Google Maps for `query`, scroll the results feed, and return
    the unique listing URLs found (capped at MAX_RESULTS_PER_QUERY)."""
    url = f"https://www.google.com/maps/search/{quote(query)}?hl=en"
    page.goto(url, timeout=30000)
    accept_consent(page)

    feed = page.locator('div[role="feed"]').first
    try:
        feed.wait_for(timeout=15000)
    except PlaywrightTimeoutError:
        print(f"  no results feed found for query: {query!r} -- skipping")
        return []

    seen: set[str] = set()
    stagnant_rounds = 0

    while len(seen) < MAX_RESULTS_PER_QUERY and stagnant_rounds < MAX_SCROLL_ATTEMPTS_WITHOUT_NEW:
        cards = feed.locator('a[href^="https://www.google.com/maps/place"]')
        hrefs = {cards.nth(i).get_attribute("href") for i in range(cards.count())}
        hrefs.discard(None)

        if len(hrefs) <= len(seen):
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        seen = hrefs

        box = feed.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.wheel(0, 1800)
        else:
            feed.evaluate("el => el.scrollTop = el.scrollHeight")
        human_delay(*SCROLL_DELAY_RANGE)

    return list(seen)[:MAX_RESULTS_PER_QUERY]


def extract_place_details(page, href: str) -> dict | None:
    """Load a single Maps listing and pull out its details. Returns None if
    the listing already has a website linked (i.e. it's not a prospect)."""
    page.goto(href, timeout=30000)
    page.wait_for_selector("h1", timeout=15000)

    if page.locator('a[data-item-id="authority"]').count() > 0:
        return None  # has a website listed on Google -- not a prospect

    name = page.locator("h1").first.inner_text().strip()

    phone = ""
    phone_btn = page.locator('button[data-item-id^="phone:tel:"]').first
    if phone_btn.count() > 0:
        phone = (phone_btn.get_attribute("aria-label") or "").replace("Phone:", "").strip()

    address = ""
    addr_btn = page.locator('button[data-item-id="address"]').first
    if addr_btn.count() > 0:
        address = (addr_btn.get_attribute("aria-label") or "").replace("Address:", "").strip()

    main_text = ""
    try:
        main_text = page.locator('div[role="main"]').first.inner_text()
    except Exception:
        pass

    rating_match = re.search(r"(\d\.\d)\s", main_text)
    review_match = re.search(r"([\d,]+)\s+review", main_text, re.IGNORECASE)

    return {
        "name": name,
        "address": address,
        "phone": phone,
        "rating": rating_match.group(1) if rating_match else "",
        "review_count": int(review_match.group(1).replace(",", "")) if review_match else 0,
        "google_maps_url": page.url,
    }


def attempt_enrich(business_name: str, address: str) -> dict:
    """Best-effort email + 'unlisted website' lookup via Google Custom Search.

    Returns blanks (with a manual-lookup note) if CSE keys aren't configured
    or nothing useful is found -- this is the deliberate manual-fallback path.
    """
    empty = {"email": "", "possible_unlisted_website": "", "notes": "manual lookup needed"}

    if not GOOGLE_CSE_ID or not GOOGLE_CSE_KEY:
        return empty

    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_CSE_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": f"{business_name} {address}",
                "num": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except requests.RequestException:
        return empty

    found_site = ""
    found_email = ""

    for item in items:
        link = item.get("link", "")
        domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0].lower()
        snippet = item.get("snippet", "") or ""

        m = EMAIL_RE.search(snippet)
        if m and not found_email:
            found_email = m.group(0)

        if domain and domain not in DIRECTORY_DOMAINS and not found_site:
            found_site = link

    # If we found a plausible independent site, try its homepage for an email.
    if found_site and not found_email:
        try:
            page = requests.get(found_site, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            m = EMAIL_RE.search(page.text[:200_000])
            if m:
                found_email = m.group(0)
        except requests.RequestException:
            pass

    if not found_site and not found_email:
        return empty

    notes = []
    if found_site:
        notes.append("possible unlisted website found -- verify before pitching")
    if not found_email:
        notes.append("no email found automatically -- manual lookup needed")

    return {
        "email": found_email,
        "possible_unlisted_website": found_site,
        "notes": "; ".join(notes),
    }


def run_scan() -> dict:
    rows: dict[str, dict] = {}
    chromium_path = find_prebuilt_chromium()

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if chromium_path:
            launch_kwargs["executable_path"] = chromium_path
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        for qi, query in enumerate(QUERIES):
            print(f"Searching: {query}")
            hrefs = collect_listing_urls(page, query)
            print(f"  found {len(hrefs)} listings, checking each for a website...")

            for href in hrefs:
                try:
                    details = extract_place_details(page, href)
                except PlaywrightTimeoutError:
                    print("  timed out loading a listing, skipping")
                    continue
                except Exception as exc:
                    print(f"  failed to parse a listing ({exc}), skipping")
                    continue
                finally:
                    human_delay(*CARD_DELAY_RANGE)

                if details is None:
                    continue  # has a website -- not a prospect

                place_id = hashlib.md5(
                    f"{details['name']}|{details['address']}".encode()
                ).hexdigest()
                if place_id in rows:
                    continue

                enrichment = attempt_enrich(details["name"], details["address"])
                rows[place_id] = {
                    "name": details["name"],
                    "query": query,
                    "address": details["address"],
                    "phone": details["phone"],
                    "rating": details["rating"],
                    "review_count": details["review_count"],
                    "google_maps_url": details["google_maps_url"],
                    "email": enrichment["email"],
                    "possible_unlisted_website": enrichment["possible_unlisted_website"],
                    "pitch_angle": (
                        "site not linked on Google Maps"
                        if enrichment["possible_unlisted_website"]
                        else "no website"
                    ),
                    "notes": enrichment["notes"],
                }

            if qi < len(QUERIES) - 1:
                human_delay(*QUERY_DELAY_RANGE)

        context.close()
        browser.close()

    return rows


def main():
    rows = run_scan()
    sorted_rows = sorted(rows.values(), key=lambda r: r["review_count"], reverse=True)

    os.makedirs("output", exist_ok=True)
    out_path = os.path.join("output", "prospects.csv")
    fieldnames = [
        "name", "query", "address", "phone", "rating", "review_count",
        "google_maps_url", "email", "possible_unlisted_website", "pitch_angle", "notes",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print(f"\nWrote {len(sorted_rows)} no-website prospects to {out_path}")
    print("Top of the CSV = most-reviewed businesses with zero website. Call these first.")


if __name__ == "__main__":
    main()
