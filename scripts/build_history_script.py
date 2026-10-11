#!/usr/bin/env python3
"""Build the narration script for a history topic.

Usage: build_history_script.py <topic_id> <out_txt>
- Loads islamic_history_topics.json, finds the topic (must have scripted=true).
- Loads history_scripts/<topic_id>.txt (full Urdu narration, <ar>...</ar> for Arabic).
- Validates minimum length (~17500 chars ≈ 30 min at -8% rate).
- Writes the script text to <out_txt> and topic meta to <out_txt>.meta.json.

Zero AI tokens: scripts are pre-authored and stored in the repo.
"""
import json
import os
import re
import sys

MIN_CHARS = 17000  # ≈ 29-30 min at ur-PK -8% (~585 chars/min)


def main():
    topic_id, out_txt = sys.argv[1], sys.argv[2]
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bank = json.load(open(os.path.join(base, "islamic_history_topics.json"),
                          encoding="utf-8"))
    topic = next((t for t in bank["topics"] if t["id"] == topic_id), None)
    if not topic:
        print(f"ERROR: topic {topic_id} not in bank", file=sys.stderr)
        sys.exit(1)
    if not topic.get("scripted"):
        print(f"ERROR: topic {topic_id} has no complete script yet",
              file=sys.stderr)
        sys.exit(1)

    script_path = os.path.join(base, "history_scripts", f"{topic_id}.txt")
    text = open(script_path, encoding="utf-8").read().strip()
    # strip <ar> tags for char count (they're short anyway)
    plain = re.sub(r"</?ar>", "", text)
    n = len(plain)
    print(f"topic={topic_id} chars={n} est_min={n/585:.1f}")
    if n < MIN_CHARS:
        print(f"WARNING: script shorter than {MIN_CHARS} chars", file=sys.stderr)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(text)
    meta = {
        "id": topic_id,
        "title_urdu": topic["title_urdu"],
        "title_en": topic["title_en"],
        "era": topic["era"],
        "backgrounds": topic["backgrounds"],
        "seo": topic["seo"],
        "chars": n,
    }
    with open(out_txt + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"OK: {out_txt}")


if __name__ == "__main__":
    main()
