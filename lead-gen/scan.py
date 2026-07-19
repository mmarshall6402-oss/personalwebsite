"""
Scan Google Maps (via the Places API) for businesses with no website listed,
sorted by review count (most-reviewed first). Writes output/prospects.csv.

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in GOOGLE_API_KEY (and optionally the CSE keys)

Usage:
    Edit QUERIES below, then:
    python scan.py
"""

import csv
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Edit these for whatever neighborhoods/niches you're prospecting -------
QUERIES = [
    "plumbers in Park Slope Brooklyn NY",
    "hair salons in Astoria Queens NY",
    "auto repair shops in Jersey City NJ",
]
# ----------------------------------------------------------------------------

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.websiteUri",
        "places.googleMapsUri",
    ]
)

MAX_PAGES_PER_QUERY = 3  # Places API returns up to 20 results/page; caps cost.

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


def search_places(query: str) -> list[dict]:
    if not GOOGLE_API_KEY:
        raise SystemExit("GOOGLE_API_KEY is not set. Copy .env.example to .env and fill it in.")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": FIELD_MASK + ",nextPageToken",
    }

    results = []
    body = {"textQuery": query}
    for page in range(MAX_PAGES_PER_QUERY):
        resp = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("places", []))

        next_token = data.get("nextPageToken")
        if not next_token:
            break
        # Google requires a short delay before a page token becomes valid.
        time.sleep(2)
        body = {"textQuery": query, "pageToken": next_token}

    return results


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


def main():
    rows = {}  # dedupe by place id

    for query in QUERIES:
        print(f"Searching: {query}")
        places = search_places(query)
        for place in places:
            place_id = place.get("id")
            if not place_id or place_id in rows:
                continue
            if place.get("websiteUri"):
                continue  # has a website listed on Google -- not a prospect

            name = place.get("displayName", {}).get("text", "")
            address = place.get("formattedAddress", "")
            enrichment = attempt_enrich(name, address)

            rows[place_id] = {
                "name": name,
                "query": query,
                "address": address,
                "phone": place.get("nationalPhoneNumber", ""),
                "rating": place.get("rating", ""),
                "review_count": place.get("userRatingCount", 0),
                "google_maps_url": place.get("googleMapsUri", ""),
                "email": enrichment["email"],
                "possible_unlisted_website": enrichment["possible_unlisted_website"],
                "pitch_angle": (
                    "site not linked on Google Maps"
                    if enrichment["possible_unlisted_website"]
                    else "no website"
                ),
                "notes": enrichment["notes"],
            }

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
