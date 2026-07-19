# Lead-gen: no-website business prospecting

Finds local businesses on Google Maps with no website listed, sorted by
review count, then generates outreach scripts to pitch them on a new site.

`scan.py` works by driving headless Chromium (Playwright) over the real
Google Maps site, rather than calling the official Places API. That means:

- **No API key or cost** for the search step.
- **Against Google's Terms of Service**, and inherently fragile -- Maps'
  HTML changes without notice, so if the script starts finding 0 results,
  the selectors in `scan.py` (`extract_place_details`, `collect_listing_urls`)
  likely need updating to match Maps' current markup.
- **Runs with pacing by default** (randomized delays between scrolls,
  listing clicks, and queries; capped results per query) to reduce the
  chance of the scraping IP getting rate-limited or blocked. If you're
  getting blocked, widen the `*_DELAY_RANGE` constants and lower
  `MAX_RESULTS_PER_QUERY` at the top of `scan.py`. If runs feel too slow
  and you're willing to accept more block risk, tighten them.

## Setup

```bash
cd lead-gen
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill in `.env` (optional):

- **`GOOGLE_CSE_ID`** / **`GOOGLE_CSE_KEY`** -- a Programmable Search
  Engine (set to search the whole web) + its JSON API key. When set,
  `scan.py` automates the "10-second Google check": it looks for a website
  that exists but isn't linked on the business's Google listing, and
  best-effort scrapes a contact email. Free tier is 100 queries/day. Leave
  blank and every row will just be flagged for manual lookup instead.

## Usage

1. Edit `QUERIES` at the top of `scan.py` for whatever neighborhoods/niches
   you're targeting, e.g. `"plumbers in Park Slope Brooklyn NY"`.
2. Run the scan:

   ```bash
   python scan.py
   ```

   Writes `output/prospects.csv`. Top of the CSV = most-reviewed businesses
   with zero website listed -- call these first. If a row has
   `possible_unlisted_website` filled in, the business likely already has a
   site that's just not linked from Google -- pitch "get your site linked
   and found on Google" instead of "you need a website."

3. Generate outreach scripts:

   ```bash
   python outreach.py --limit 20
   ```

   Writes one `.txt` file per business to `output/outreach/`, each with a
   phone-call script and a walk-in script tailored to the pitch angle. These
   are drafts to read from or adapt -- nothing is sent automatically.
