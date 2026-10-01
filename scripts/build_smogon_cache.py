import gzip
import json
import os
from datetime import date

import requests


def previous_month(today: date) -> str:
    """Smogon publishes last month's stats early each month: Oct 2026 -> '2026-09'."""
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


MONTH = os.environ.get("SMOGON_MONTH") or previous_month(date.today())
FORMAT = "gen9ou-1695"
TOP_N = 30
URL = f"https://www.smogon.com/stats/{MONTH}/{FORMAT}.txt.gz"
OUT_PATH = "data/smogon_usage.json"
NAME_FIXES = {
    "ogerpon-wellspring": "ogerpon-wellspring-mask",
    "ogerpon-hearthflame": "ogerpon-hearthflame-mask",
    "ogerpon-cornerstone": "ogerpon-cornerstone-mask",
}


def to_pokeapi_name(smogon_name: str) -> str:
    """'Great Tusk' -> 'great-tusk', 'Mr. Mime' -> 'mr-mime'."""
    name = smogon_name.lower().replace(" ", "-")
    for ch in ".':%":
        name = name.replace(ch, "")
    return NAME_FIXES.get(name, name)


def parse_usage(text: str, top_n: int) -> list[dict]:
    """Pull (rank, name, usage %) rows out of Smogon's usage table."""
    rows = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 4 or not cols[1].isdigit():
            continue
        rows.append(
            {
                "rank": int(cols[1]),
                "smogon_name": cols[2],
                "name": to_pokeapi_name(cols[2]),
                "usage": float(cols[3].rstrip("%")),
            }
        )
        if len(rows) == top_n:
            break
    return rows


def main() -> None:
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    text = gzip.decompress(r.content).decode("utf-8")
    rows = parse_usage(text, TOP_N)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"month": MONTH, "format": FORMAT, "top": rows}, f, indent=2)
    print(f"Saved top {len(rows)} from {FORMAT} {MONTH}")
    for row in rows[:5]:
        print(row)


if __name__ == "__main__":
    main()
