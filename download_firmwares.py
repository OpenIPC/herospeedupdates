#!/usr/bin/env python3
"""Archive Herospeed's firmware builds as release assets.

  GH_TOKEN=... python download_firmwares.py [--max-per-run N] [--commit-every N] [--dry-run]

For every file items.json (refresh.py) links, the server is asked for its
size and Last-Modified; a file whose pair the archive already holds is
skipped. Otherwise it is downloaded, checked against the size the server
announced, and uploaded to this repository's "firmware-archive" release as
<build>.zip -- or <build>__<sha256[:8]>.zip when Herospeed has replaced a
file under the same name, so each version stays where it was.

Herospeed gives no checksum: the sha256 recorded is of the file as fetched.
Several rows link one file (KL5R/KL5RC and KL5AD share
KL5_1ND_BVHB_V2.0.13.260306_R2.zip): it is archived once.

Outcomes, in archive/index.json keyed by the build's name:
  revisions[]    archived: asset_url, sha256, size, last_modified, archived_at
  unavailable[]  the server answers 403/404/410 for the file
A download that is cut short is a transient failure: nothing is recorded
and the file is tried again next run.

Without --dry-run this uploads to the real release and commits and pushes
archive/index.json itself (every --commit-every successes).
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ITEMS = ROOT / "items.json"
INDEX_PATH = ROOT / "archive" / "index.json"
RELEASE_TAG = "firmware-archive"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/128.0 Safari/537.36"}


class Unavailable(Exception):
    """The server no longer has the file."""


def load_index():
    if INDEX_PATH.exists():
        with INDEX_PATH.open() as f:
            return json.load(f)
    return {}


def save_index(index):
    INDEX_PATH.parent.mkdir(exist_ok=True)
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(index, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(INDEX_PATH)


def head(url):
    """(size, Last-Modified) the server announces for url."""
    r = requests.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
    if r.status_code in (403, 404, 410):
        raise Unavailable(f"server answered {r.status_code}")
    r.raise_for_status()
    return int(r.headers.get("Content-Length") or -1), r.headers.get("Last-Modified") or ""


def download(url, dest):
    sha, size = hashlib.sha256(), 0
    with requests.get(url, headers=HEADERS, stream=True, timeout=300) as r:
        if r.status_code in (403, 404, 410):
            raise Unavailable(f"server answered {r.status_code}")
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                sha.update(chunk)
                size += len(chunk)
    return sha.hexdigest(), size


def gh(*args, check=True, capture=False):
    return subprocess.run(["gh", *args], check=check, capture_output=capture, text=True)


def ensure_release_exists():
    if gh("release", "view", RELEASE_TAG, check=False, capture=True).returncode == 0:
        return
    gh("release", "create", RELEASE_TAG, "--title", "Firmware archive",
       "--notes", "Mirror of Herospeed's firmware for Longse's IP cameras. See archive/index.json for each build's asset.")


def existing_release_assets():
    """Asset name -> sha256 ("" when GitHub reports none)."""
    res = gh("release", "view", RELEASE_TAG, "--json", "assets", check=False, capture=True)
    if res.returncode != 0:
        raise RuntimeError(f"cannot list {RELEASE_TAG} assets: {res.stderr.strip()}")
    return {a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in json.loads(res.stdout).get("assets", [])}


def repo_slug():
    if slug := os.environ.get("GITHUB_REPOSITORY"):
        return slug
    res = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", check=False, capture=True)
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "OpenIPC/herospeedupdates"


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, cwd=ROOT, capture_output=True, text=True)


def commit_and_push(count):
    git("add", str(INDEX_PATH.relative_to(ROOT)))
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    git("commit", "-m", f"archive: +{count} firmware builds")
    git("push", check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-per-run", type=int, default=100)
    ap.add_argument("--commit-every", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = json.load(ITEMS.open())["rows"]
    files = {}
    for row in rows:
        files.setdefault(row["url"], row["build"])
    index = load_index()
    if not args.dry_run:
        ensure_release_exists()
    try:
        assets = existing_release_assets()
    except RuntimeError as e:
        if not args.dry_run:
            print(f"Aborting: {e}", file=sys.stderr)
            return 1
        assets = {}
    slug = repo_slug()
    now = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = failures = gone = since = 0
    for url, build in sorted(files.items(), key=lambda kv: kv[1]):
        if args.max_per_run > 0 and done >= args.max_per_run:
            break
        entry = index.setdefault(build, {})
        try:
            size, modified = head(url)
        except Unavailable as e:
            if not any(u.get("url") == url for u in entry.get("unavailable", [])):
                print(f"[{build}] {e}; recorded as unavailable")
                entry.setdefault("unavailable", []).append({"url": url, "checked_at": now()})
                gone += 1
                save_index(index)
            continue
        except requests.RequestException as e:
            failures += 1
            print(f"[{build}] HEAD failed: {e!r}", file=sys.stderr)
            continue
        if any(r["size"] == size and r.get("last_modified") == modified for r in entry.get("revisions", [])):
            continue
        print(f"[{build}] {size} bytes, {modified} -> {url}")
        if args.dry_run:
            done += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                name = build + ".zip"
                path = Path(td) / name
                sha, got = download(url, path)
                if size >= 0 and got != size:
                    raise RuntimeError(f"{got} bytes, the server announced {size}")
                if assets.get(name) == sha or sha in {r["sha256"] for r in entry.get("revisions", [])}:
                    # Same bytes, newer Last-Modified: nothing new to keep.
                    name = next((r["asset"] for r in entry.get("revisions", []) if r["sha256"] == sha), name)
                else:
                    if name in assets:
                        name = f"{build}__{sha[:8]}.zip"
                        path = path.rename(Path(td) / name)
                    gh("release", "upload", RELEASE_TAG, str(path))
                    assets[name] = sha
        except Unavailable as e:
            print(f"  {e}; recorded as unavailable")
            entry.setdefault("unavailable", []).append({"url": url, "checked_at": now()})
            gone += 1
            save_index(index)
            continue
        except Exception as e:
            failures += 1
            print(f"  FAILED: {e!r}", file=sys.stderr)
            continue
        revs = entry.setdefault("revisions", [])
        same = next((r for r in revs if r["sha256"] == sha), None)
        if same:
            same["last_modified"] = modified
        else:
            revs.append({"asset": name, "sha256": sha, "size": got, "last_modified": modified, "source_url": url,
                         "asset_url": f"https://github.com/{slug}/releases/download/{RELEASE_TAG}/{name}",
                         "archived_at": now()})
        save_index(index)
        done += 1
        since += 1
        if since >= args.commit_every:
            commit_and_push(since)
            since = 0
    if since and not args.dry_run:
        commit_and_push(since)
    print(f"\nDone. archived={done} unavailable={gone} failures={failures}")
    return 1 if done == 0 and gone == 0 and failures else 0


if __name__ == "__main__":
    sys.exit(main())
