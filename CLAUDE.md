# CLAUDE.md

A mirror of Herospeed's firmware for Longse's IP cameras, for OpenIPC: data (`items.json`,
`archive/index.json`) and three scripts run by `.github/workflows/weekly-update.yml`. Most commits are made
by `herospeedupdates-bot`.

- `python refresh.py` — rewrite `items.json` from Herospeed's two list pages (catid 281 current, 344
  discontinued); all-or-nothing.
- `GH_TOKEN=$(gh auth token) python download_firmwares.py --dry-run` — the plan; without `--dry-run` it
  uploads to the real `firmware-archive` release and commits and pushes `archive/index.json` itself.
- `python push_openipc_org.py --dry-run` — the push's size. The real push needs the workflow's OIDC token;
  openipc.org accepts it only from `weekly-update.yml` on `main` (the contract is
  `service/internal/vendorfw/PUSH.md` in OpenIPC/website, source `herospeedupdates`; `module` is required).

Gotchas:

- The list pages are tables with rowspans: the last three cells of a row (firmware, time, link) are its
  own, the first three (series, resolution, solution) carried down.
- The pages misprint: doubled slashes in links, a `SigmaStaar` folder (404; the file is under
  `SigmaStar`), versions with spaces for dots in the Firmware column. The link's file name is the build.
- The list's time is China time (+08:00).
- The `module` (the solution's first code) must be the code openipc.org's herospeed snapshot gives the
  board (`tools/board-donors/herospeed_snapshot.py` in OpenIPC/website reads the same lists the same way).
