#!/usr/bin/env python
"""Append new publications from Google Scholar to _bibliography/papers.bib.

Reads `scholar_userid` from _data/socials.yml, lists the profile's publications,
and appends a BibTeX entry for each one that is not already in papers.bib
(matched by its `google_scholar_id` field, or by title). Existing entries are
never modified, so manual edits (selected={true}, pdf links, abbr, ...) are kept.
"""

import os
import re
import sys
import time

import yaml
from scholarly import scholarly

SOCIALS_FILE = "_data/socials.yml"
BIB_FILE = "_bibliography/papers.bib"


def load_user_id() -> str:
    with open(SOCIALS_FILE) as f:
        user_id = (yaml.safe_load(f) or {}).get("scholar_userid")
    if not user_id:
        sys.exit(f"No 'scholar_userid' in {SOCIALS_FILE}")
    return user_id


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def existing_ids_and_titles(bib_text: str):
    ids = set(re.findall(r"google_scholar_id\s*=\s*\{([^}]*)\}", bib_text))
    titles = {norm_title(t) for t in re.findall(r"\btitle\s*=\s*\{(.*)\},?\s*$", bib_text, flags=re.M)}
    return ids, titles


def bib_escape(value: str) -> str:
    return str(value).replace("&", r"\&").replace("%", r"\%").replace("\n", " ").strip()


def make_key(bib: dict, used: set) -> str:
    first_author = (bib.get("author") or "anon").split(" and ")[0].split()[-1]
    first_word = next((w for w in re.findall(r"[A-Za-z]+", bib.get("title", "")) if len(w) > 3), "paper")
    base = re.sub(r"[^a-z0-9]", "", f"{first_author}{bib.get('pub_year', '')}{first_word}".lower()) or "paper"
    key, n = base, 2
    while key in used:
        key, n = f"{base}{chr(ord('a') + n - 2)}", n + 1
    used.add(key)
    return key


def to_bibtex(pub: dict, key: str) -> str:
    bib = pub.get("bib", {})
    venue = bib.get("journal") or bib.get("conference") or bib.get("booktitle") or bib.get("venue") or bib.get("citation")
    is_conf = bool(bib.get("conference") or bib.get("booktitle"))
    entry_type = "inproceedings" if is_conf else "article"
    fields = {
        "title": bib.get("title"),
        "author": bib.get("author"),
        "booktitle" if is_conf else "journal": venue,
        "year": bib.get("pub_year"),
        "volume": bib.get("volume"),
        "number": bib.get("number"),
        "pages": bib.get("pages"),
        "abstract": bib.get("abstract"),
        "html": pub.get("pub_url"),
        "google_scholar_id": pub.get("author_pub_id", "").split(":")[-1],
        "bibtex_show": "true",
    }
    lines = [f"  {k} = {{{bib_escape(v)}}}" for k, v in fields.items() if v]
    return f"@{entry_type}{{{key},\n" + ",\n".join(lines) + "\n}\n"


def fill_with_retry(pub: dict, attempts: int = 3) -> dict:
    """Fetch the detail page (full author list, venue, abstract).

    Google Scholar sometimes serves a block page instead; after a few tries,
    fall back to the summary data (title, year, citation string) so the paper
    still shows up. Add the missing fields to papers.bib by hand if needed.
    """
    for i in range(attempts):
        try:
            return scholarly.fill(pub)
        except Exception as e:  # scholarly raises AttributeError etc. on block pages
            print(f"    detail fetch failed ({type(e).__name__}), attempt {i + 1}/{attempts}")
            time.sleep(10 * (i + 1))
    print("    using summary data only (no author list); edit papers.bib to complete it")
    return pub


def main() -> None:
    user_id = load_user_id()
    bib_text = open(BIB_FILE).read() if os.path.exists(BIB_FILE) else ""
    known_ids, known_titles = existing_ids_and_titles(bib_text)
    used_keys = set(re.findall(r"@\w+\{([^,]+),", bib_text))

    print(f"Fetching Google Scholar profile {user_id} ...")
    author = scholarly.fill(scholarly.search_author_id(user_id), sections=["publications"])
    pubs = author.get("publications", [])
    print(f"Profile lists {len(pubs)} publications.")

    new_entries = []
    for pub in pubs:
        pub_id = pub.get("author_pub_id", "").split(":")[-1]
        title = pub.get("bib", {}).get("title", "")
        if pub_id in known_ids or norm_title(title) in known_titles:
            continue
        print(f"  + {title}")
        pub = fill_with_retry(pub)
        new_entries.append(to_bibtex(pub, make_key(pub.get("bib", {}), used_keys)))

    if not new_entries:
        print("No new publications.")
        return
    with open(BIB_FILE, "a") as f:
        if bib_text and not bib_text.endswith("\n\n"):
            f.write("\n")
        f.write("\n".join(new_entries))
    print(f"Added {len(new_entries)} publication(s) to {BIB_FILE}.")


if __name__ == "__main__":
    main()
