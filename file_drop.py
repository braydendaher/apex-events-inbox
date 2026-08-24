"""
File a drop the scout could not push itself.

The routine runs in a sandbox that may only have READ access to this repo. When
that happens it still does the full search and prints the JSON in its run
output, between two marker lines. This takes that text and files it properly:
fresh id, both files written, committed and pushed. The Worker picks it up on
its next half-hourly cron exactly as if the scout had pushed it.

    python file_drop.py paste.txt        # a file holding the run output
    python file_drop.py                  # or paste on stdin, then Ctrl+Z Enter

It accepts the raw run output with the BEGIN/END markers around the JSON, or a
bare JSON object. The id is always rewritten to today's date plus the next free
run number, because the Worker keys "already handled" off the id and silently
ignores one it has seen before. Reusing an id is the one mistake that fails
without any visible error.

Nothing here trusts the content. Every event still goes through the Worker's
own gates: the publish window, DST-correct epochs, geocoding, dedupe, and the
source-link check that opens each link and confirms the page really backs the
event up.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BEGIN = "----- DROP JSON BEGIN -----"
END = "----- DROP JSON END -----"


def extract(text: str) -> dict:
    """Pull the JSON object out of a run log, or parse it directly."""
    if BEGIN in text and END in text:
        text = text.split(BEGIN, 1)[1].split(END, 1)[0]
    text = text.strip()
    if not text.startswith("{"):
        # Fall back to the outermost braces, which survives stray log lines
        # wrapped around the object.
        start, stop = text.find("{"), text.rfind("}")
        if start == -1 or stop == -1:
            sys.exit("No JSON object found. Paste the run output or the JSON itself.")
        text = text[start:stop + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        sys.exit(f"That is not valid JSON: {err}")


def next_id(day: str) -> str:
    """Today's date plus the next unused number, tagged `manual`.

    Deliberately NOT the scout's own `<date>-runN` shape. If a salvaged drop
    reused an id the scout had already used, the Worker would see an id it has
    handled and ignore the file completely, with nothing logged and no error
    anywhere. A separate namespace makes that collision impossible.
    """
    drops = os.path.join(HERE, "drops")
    existing = set(os.listdir(drops)) if os.path.isdir(drops) else set()
    n = 1
    while f"events-{day}-manual{n}.json" in existing:
        n += 1
    return f"{day}-manual{n}"


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=HERE, check=True)


def main() -> None:
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    drop = extract(raw)

    events = drop.get("events")
    if not isinstance(events, list) or not events:
        sys.exit("That drop has no events in it.")
    if len(events) > 25:
        sys.exit(f"{len(events)} events, but the Worker takes at most 25 per drop. Split it.")

    day = dt.date.today().isoformat()
    drop["id"] = next_id(day)
    drop["dryRun"] = bool(drop.get("dryRun", False))

    body = json.dumps(drop, indent=2, ensure_ascii=False) + "\n"
    os.makedirs(os.path.join(HERE, "drops"), exist_ok=True)
    copy = os.path.join("drops", f"events-{drop['id']}.json")
    for path in (os.path.join(HERE, "latest.json"), os.path.join(HERE, copy)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    names = [e.get("name", "?") for e in events]
    print(f"Filed {len(events)} event(s) as {drop['id']}"
          + (" (DRY RUN, nothing will be written)" if drop["dryRun"] else ""))
    for n in names:
        print(f"  - {n}")

    git("add", "latest.json", copy)
    git("commit", "-q", "-m", f"Drop {drop['id']}: {len(events)} event(s) from a blocked scout run")
    git("push", "-q", "origin", "main")
    print("\nPushed. The Worker cron runs every 30 minutes; it will pick this up on the next tick.")
    print("Check the result with:")
    print("  npx wrangler d1 execute apex-app-db --remote --command "
          f"\"SELECT summary FROM relay_processed WHERE id='relay:{drop['id']}';\"")


if __name__ == "__main__":
    main()
