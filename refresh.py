#!/usr/bin/env python3
"""Refresh items.json: every firmware build Herospeed lists for Longse's IP cameras.

  python refresh.py

Herospeed (herospeed.net) is Longse's firmware house. Its download centre
lists the IP camera firmware in two tables, current products and
discontinued ones:

  https://www.herospeed.net/en/index.php?m=content&c=index&a=lists&catid=281
  https://www.herospeed.net/en/index.php?m=content&c=index&a=lists&catid=344

Each row is one build for one solution, the board a Longse camera's model
name ends in (DMSAKL5RC is housing DMSA on board KL5RC):

  list        current or discontinued
  series      Eco, Value, Pro, Wi-Fi IPC, PTZ, AI-ISP, ...
  resolution  2MP, 4/5MP, ...
  solution    as the list writes it: KL5R/KL5RC, RL200/RL200WH(NAND), or
              "/" when it names no board
  module      the solution's first code (KL5R), the board openipc.org's
              catalogue files the build under; absent when it names none
  build       the file's name without .zip (KL5_1ND_BVHB_V2.0.13.260306_R2)
  time        the list's date for it, China time
  url         the file, as the server answers it

The page's own misprints are set right: doubled slashes in a link, the
SigmaStaar folder (a 404; the file is under SigmaStar), a version written
with spaces for dots in the Firmware column (the link's name is taken).

The write is all-or-nothing: an error, a list that is not there, or a row
that cannot be read leaves items.json untouched and exits non-zero.
"""

import html
import json
import os
import re
import sys
import urllib.parse
from html.parser import HTMLParser

import requests

LIST = "https://www.herospeed.net/en/index.php?m=content&c=index&a=lists&catid="
LISTS = {"current": 281, "discontinued": 344}
OUT = "items.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/128.0 Safari/537.36"}
CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]*$")


class Table(HTMLParser):
    """The list's rows: each a list of cells (text, href, rowspan)."""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "href": None, "span": int(a.get("rowspan") or 1)}
        elif tag == "a" and self.cell is not None and a.get("href"):
            self.cell["href"] = a["href"]

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def rows_of(page):
    """(series, resolution, solution, time, href) per row: the last three cells
    (firmware, time, link) are each row's own, the first three carried down
    by their rowspan."""
    t = Table()
    t.feed(page)
    out, carry = [], [None, None, None]
    for row in t.rows:
        if len(row) < 3 or not row[-1]["href"]:
            continue
        lead, own = row[:-3], row[-3:]
        free = [i for i in range(3) if not (carry[i] and carry[i][1] > 0)]
        if len(lead) != len(free):
            raise ValueError(f"row {[c['text'] for c in row]}: {len(lead)} leading cells for {len(free)} free columns")
        for i, c in zip(free, lead):
            carry[i] = [c, c["span"]]
        vals = [" ".join(carry[i][0]["text"].split()) for i in range(3)]
        for i in range(3):
            carry[i][1] -= 1
        out.append((*vals, " ".join(own[1]["text"].split()), own[2]["href"]))
    return out


def file_url(href):
    u = urllib.parse.urljoin(LIST, html.unescape(href.strip()))
    parts = urllib.parse.urlsplit(u)
    path = re.sub(r"/{2,}", "/", parts.path).replace("/SigmaStaar/", "/SigmaStar/")
    return urllib.parse.urlunsplit(parts._replace(path=path))


def module_of(solution):
    """The first code a Solution cell names (RL200/RL200WH(NAND) -> RL200), or
    None when it names no board ("/", "3MP")."""
    cell = re.sub(r"\((EMMC|NAND)\)\s*$", "", solution.strip(), flags=re.I)
    codes = [re.sub(r"[^A-Z0-9-]+", "-", c.strip().upper()).strip("-") for c in cell.split("/") if c.strip()]
    if not codes or not CODE.match(codes[0]) or re.fullmatch(r"\d+MP", codes[0]):
        return None
    return codes[0]


def main():
    rows = []
    try:
        for name, catid in LISTS.items():
            r = requests.get(LIST + str(catid), headers=HEADERS, timeout=60)
            r.raise_for_status()
            listed = rows_of(r.content.decode("utf-8", "replace"))
            if not listed:
                raise ValueError(f"the {name} list has no rows")
            for series, res, solution, time, href in listed:
                url = file_url(href)
                build = os.path.basename(urllib.parse.urlsplit(url).path)
                if not build.lower().endswith(".zip") or not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", time):
                    raise ValueError(f"row {solution} {href} {time}: not a build")
                row = {"list": name, "series": series, "resolution": res, "solution": solution,
                       "build": build[:-4], "time": time, "url": url}
                if module_of(solution):
                    row["module"] = module_of(solution)
                rows.append(row)
    except (requests.RequestException, ValueError) as e:
        sys.exit(f"refresh: {e}; {OUT} left as it was")
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"source": LIST, "rows": rows}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUT)
    print(f"refresh: {len(rows)} rows, {len({r['url'] for r in rows})} files")


if __name__ == "__main__":
    main()
