"""
Generate phone-call and walk-in outreach scripts from output/prospects.csv.

Usage:
    python outreach.py               # generate for every row
    python outreach.py --limit 20    # generate for the top 20 (by review count)
"""

import argparse
import csv
import os
import re

PHONE_SCRIPT = """PHONE SCRIPT -- {name}
{underline}

Hi, is this {name}? ... Hi, my name is [YOUR NAME], I'm a local web developer.

I was looking up {niche} in the area on Google Maps and noticed {name} has
{review_count} reviews -- that's a great reputation -- but {pitch_line}

I build simple, affordable websites for local businesses like yours, so
customers who find you on Google can actually see your hours, services,
and get in touch. Would you be open to a quick 5-minute chat about what
that could look like for {name}?

[If yes -> book a callback time or set up a quick call now]
[If no -> "No worries, thanks for your time!" Leave door open: "If that
 ever changes, feel free to reach out."]
"""

WALK_IN_SCRIPT = """WALK-IN SCRIPT -- {name}
{underline}

Hi there, sorry to bother you -- quick question. Are you the owner or
manager here?

[Once confirmed]

I noticed {name} doesn't have {pitch_line_walkin} I help local businesses
like yours get a simple, professional website up so people searching on
Google can find your hours, services, and contact info without having to
call and ask.

Would it be alright if I left you my card / sent over a quick example of
what that could look like for {name}? No pressure at all -- just wanted
to introduce myself in case it's ever useful.

[Leave card / take their email or number for follow-up]
"""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return slug or "business"


def build_scripts(row: dict) -> str:
    name = row["name"] or "this business"
    niche = row.get("query", "").strip() or "local businesses"
    review_count = row.get("review_count", "0")

    if row.get("pitch_angle") == "site not linked on Google Maps":
        pitch_line = (
            "your website isn't showing up on your Google listing, so people "
            "searching for you on Maps can't find it -- that's costing you traffic."
        )
        pitch_line_walkin = "a website linked on your Google listing --"
    else:
        pitch_line = "I couldn't find a website for you anywhere -- that's likely costing you customers."
        pitch_line_walkin = "a website --"

    underline = "-" * (len(name) + 14)

    phone = PHONE_SCRIPT.format(
        name=name, niche=niche, review_count=review_count,
        pitch_line=pitch_line, underline=underline,
    )
    walk_in = WALK_IN_SCRIPT.format(
        name=name, pitch_line_walkin=pitch_line_walkin, underline=underline,
    )

    extra = ""
    if row.get("email"):
        extra += f"\nEmail on file: {row['email']}\n"
    if row.get("possible_unlisted_website"):
        extra += f"Possible existing site (verify before pitching): {row['possible_unlisted_website']}\n"
    if row.get("notes"):
        extra += f"Notes: {row['notes']}\n"

    return phone + "\n" + walk_in + (("\n" + extra) if extra else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=os.path.join("output", "prospects.csv"))
    parser.add_argument("--limit", type=int, default=None, help="only generate for the top N rows")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit(f"{args.csv} not found -- run scan.py first.")

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.limit:
        rows = rows[: args.limit]

    out_dir = os.path.join("output", "outreach")
    os.makedirs(out_dir, exist_ok=True)

    print(f"{'Business':40} {'Reviews':>8}  Pitch angle")
    print("-" * 70)

    for i, row in enumerate(rows, start=1):
        content = build_scripts(row)
        filename = f"{i:03d}-{slugify(row['name'])}.txt"
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

        print(f"{row['name'][:40]:40} {row.get('review_count', ''):>8}  {row.get('pitch_angle', '')}")

    print(f"\nWrote {len(rows)} outreach scripts to {out_dir}/")


if __name__ == "__main__":
    main()
