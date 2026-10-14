# herospeedupdates

A self-updating mirror of the IP camera firmware [Herospeed](https://www.herospeed.net/en/) publishes for
[Longse](https://www.longse.com)'s cameras, kept for [OpenIPC](https://openipc.org). Herospeed is Longse's
firmware house; its download centre lists, for each camera board, the stock firmware for it. This
repository copies those lists and every build they link, so each one stays available with its checksum,
and tells openipc.org's board catalogue which builds exist for which board.

## Layout

| File | What it is |
|---|---|
| [`items.json`](items.json) | Both lists' rows: current products ([catid 281](https://www.herospeed.net/en/index.php?m=content&c=index&a=lists&catid=281)) and discontinued ones ([catid 344](https://www.herospeed.net/en/index.php?m=content&c=index&a=lists&catid=344)). |
| [`archive/index.json`](archive/index.json) | Build name → its archived versions: sha256, size, the server's Last-Modified and `asset_url` on this repo's `firmware-archive` release. |
| [`refresh.py`](refresh.py) | Refreshes `items.json`; all-or-nothing. |
| [`download_firmwares.py`](download_firmwares.py) | Downloads every file not archived yet (or replaced on the server since) and uploads it as a release asset. |
| [`push_openipc_org.py`](push_openipc_org.py) | Pushes the archive's list to openipc.org over a GitHub OIDC token; no secret. |

## What a row is

Each row is one build for one *solution*: the board a Longse camera is built on, which its model name ends
in. DMSAKL5RC is housing DMSA on board KL5RC; the list files `KL5_1ND_BVHB_V2.0.13.260306_R2` under
`KL5R/KL5RC`. The build's own name says nothing of the board, so the list's solution is what ties them:
`module` is its first code. A few discontinued rows give `/` or a resolution instead of a solution; they
are archived, but name no board. One file can serve several boards (KL5R and KL5AD share one).

Herospeed publishes no checksums: the sha256 is of the file as fetched, and a file is fetched again only
when the server's size or Last-Modified for it change.

## Automation

[`weekly-update.yml`](.github/workflows/weekly-update.yml) runs on Mondays and on demand: refresh the lists
and commit them, archive new builds (`--max-per-run`, 100 by default), then push the list to openipc.org
from `main` (only while the repository variable `PUSH_OPENIPC_ORG` is `true`).
