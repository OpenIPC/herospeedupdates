#!/usr/bin/env python3
"""Tell openipc.org what this mirror holds, after each weekly run.

openipc.org's board catalogue offers each Longse board the firmware builds
Herospeed lists for it. It never polls GitHub: this job pushes the whole
list once per run, and the push replaces what the site had
(https://github.com/OpenIPC/website/blob/master/service/internal/vendorfw/PUSH.md,
source herospeedupdates).

One item per board and archived file: the list's solution names the board
(module KL5R for KL5R/KL5RC), since the build's own name does not
(KL5_1ND_BVHB). A file two boards share is one item for each; a row whose
solution names no board ("/") is not pushed.

Needs `permissions: id-token: write`: the site checks a GitHub Actions OIDC
token (audience https://openipc.org) from this repository's
weekly-update.yml on main. There is no secret.

  python push_openipc_org.py [--dry-run] [--url https://dev.openipc.org/api/v1/vendor-firmware]
"""

import argparse
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL = "https://openipc.org/api/v1/vendor-firmware"
AUDIENCE = "https://openipc.org"
# KL5_1ND_BVHB_V2.0.13.260306_R2 -> KL5_1ND_BVHB, V2.0.13.260306_R2;
# RV1109_IMX335NAND_BASE_W_25.1.29.4 -> RV1109_IMX335NAND_BASE_W, 25.1.29.4
VERSION = re.compile(r"^(.+?)_(V?\d+\.\d+(?:\.\d+)*(?:[._-].*)?)$")
CHINA = dt.timezone(dt.timedelta(hours=8))


def split(build):
    m = VERSION.match(build)
    return (m.group(1), m.group(2)) if m else (build, build)


def items(rows, index):
    out, seen = [], set()
    for row in rows:
        module = row.get("module")
        if not module:
            continue
        device_type, version = split(row["build"])
        when = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CHINA).astimezone(dt.timezone.utc)
        for r in index.get(row["build"], {}).get("revisions", []):
            key = f"{module}__{r['asset']}"
            if key in seen:
                continue  # one board listed twice for the file (RL400 under Box and Fisheye)
            seen.add(key)
            out.append({"key": key, "device_type": device_type, "module": module, "app": "public",
                        "category": "wifi" if row["series"].lower().startswith("wi-fi") else "camera",
                        "version": version, "build": row["build"], "asset_url": r["asset_url"],
                        "sha256": r["sha256"], "size": r["size"],
                        "published_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def check():
    for build, want in {"KL5_1ND_BVHB_V2.0.13.260306_R2": ("KL5_1ND_BVHB", "V2.0.13.260306_R2"),
                        "RV1109_IMX335NAND_BASE_W_25.1.29.4": ("RV1109_IMX335NAND_BASE_W", "25.1.29.4"),
                        "s2l33m_imx322_W_7.1.25.1": ("s2l33m_imx322_W", "7.1.25.1"),
                        "FH8852_F23_BASE_BD_W_21.1.26.6": ("FH8852_F23_BASE_BD_W", "21.1.26.6")}.items():
        if split(build) != want:
            sys.exit(f"{build} splits as {split(build)}, want {want}")


def oidc_token():
    url, bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        sys.exit("no OIDC token: the job needs `permissions: id-token: write`")
    req = urllib.request.Request(url + "&audience=" + AUDIENCE, headers={"Authorization": "Bearer " + bearer})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the push's size and stop")
    ap.add_argument("--url", default=URL)
    args = ap.parse_args()
    check()
    with open("items.json") as f:
        rows = json.load(f)["rows"]
    with open("archive/index.json") as f:
        index = json.load(f)
    body = {"schema": 1, "source": "herospeedupdates", "items": items(rows, index)}
    if not body["items"]:
        sys.exit("nothing archived to push")
    data = gzip.compress(json.dumps(body).encode())
    print(f"{len(body['items'])} items, {len(data)} bytes gzipped")
    if args.dry_run:
        return
    token = oidc_token()
    for attempt in range(5):
        req = urllib.request.Request(args.url, data=data, method="POST", headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json", "Content-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                print(r.status, r.read().decode())
                return
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            if e.code < 500:
                sys.exit(f"refused: {e.code} {msg}")
            print(f"attempt {attempt + 1}: {e.code} {msg}")
        except urllib.error.URLError as e:
            print(f"attempt {attempt + 1}: {e.reason}")
        time.sleep(30 * (attempt + 1))
    sys.exit("openipc.org did not take the push")


if __name__ == "__main__":
    main()
