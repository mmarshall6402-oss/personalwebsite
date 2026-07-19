# Lead-gen: no-website business prospecting

Finds local businesses on Google Maps with no website listed, sorted by
review count, then generates outreach scripts to pitch them on a new site.

## Setup

```bash
cd lead-gen
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- **`GOOGLE_API_KEY`** (required) -- a Google Cloud API key with the
  **Places API (New)** enabled. Places API is metered: Text Search calls
  cost a small amount per request past the monthly free tier, so keep an
  eye on `QUERIES` length and `MAX_PAGES_PER_QUERY` in `scan.py`.
- **`GOOGLE_CSE_ID`** / **`GOOGLE_CSE_KEY`** (optional) -- a Programmable
  Search Engine (set to search the whole web) + its JSON API key. When
  set, `scan.py` automates the "10-second Google check": it looks for a
  website that exists but isn't linked on the business's Google listing,
  and best-effort scrapes a contact email. Free tier is 100 queries/day.
  Leave blank and every row will just be flagged for manual lookup instead.

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
