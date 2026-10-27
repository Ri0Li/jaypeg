# jaypeg

**jaypeg** (sounds like *JPEG*) finds RAW files under a path and writes sibling `.JPG` companions — camera RAW+JPEG style. Original RAW files are never modified.

Companions are stamped `jaypeg/<version>` in `Software` / `CreatorTool`.

<!-- ## Demo -->

## Architecture

```
host cron (optional)     docker compose
  job-start.sh  ──────►  redis  +  worker (python -m src)
  job-stop.sh   ──────►  stop worker only (redis stays up)
```

| Piece | Role |
|-------|------|
| **worker** | One-shot job: discover → queue → extract/develop → exit (`restart: "no"`) |
| **redis** | Job queue + `done` set for resume across runs (`restart: unless-stopped`) |
| **discover** | Walk `INPUT_PATH`, classify camera dual / tool companion / raw_only (exiftool stamp check on siblings) |
| **scripts/** | Host helpers: `cron-apply.sh`, `job-start.sh`, `job-stop.sh` — required for scheduled runs |

Redis remembers completed paths; it does **not** cache discover. A full-tree discover on a large NAS can take hours before any progress lines appear.

Image: [`ghcr.io/ri0li/jaypeg`](https://github.com/Ri0Li/jaypeg/pkgs/container/jaypeg) (`:latest` on `main`, also `v*` tags; `linux/amd64` + `linux/arm64`).

## Quick start

1. Clone this repo (include **`scripts/`**) and `cp .env.example .env`.
2. Set mount (`HOST_PATH` or NFS comment-toggles in [`docker-compose.yml`](docker-compose.yml)), `MODE`, `INTENT`.
3. `docker compose pull` (or `docker compose build worker`).
4. Prefer `MODE=scan` → read `./result/LATEST.md` → `dry-run` → scoped `extract`.
5. `docker compose up` — worker exits when the job finishes; redis volume keeps resume state.

> Unscoped Darktable (`develop` / fallback on a huge tree) can take a very long time and use a lot of disk.

## Modes

### extract

1. Skip camera duals (sibling JPG without this tool’s stamp). Skip tool companions unless `REWRITE=true`.
2. Try ExifTool embedded preview (`-PreviewImage`, then `-JpgFromRaw`).
3. If that fails → Darktable full-res develop (unless `DEVELOP_FALLBACK=false`), then auto-orient.
4. Stamp metadata and copy tags from the RAW. RAW files are never overwritten.

### develop

1. Same sibling / rewrite skips as extract.
2. If the RAW **has** an embedded preview → **skip**.
3. If **no** embed → Darktable full-res JPEG + auto-orient + stamp.
4. Autotune: **GPU** (`ENABLE_GPU` / `INTENT=remote`) → concurrency `1`; **CPU-only** → parallel workers by CPU/RAM. Pin with `CONCURRENCY=`.

### scan / dry-run

- **scan** — counts + `./result/LATEST.md` only (no writes).
- **dry-run** — same pipeline as extract without writing companions.

## Discover split (large trees)

By default discover walks all of `INPUT_PATH` once. On a large tree that is slow because every sibling JPG is stamp-checked with exiftool.

Set **`DISCOVER_SPLIT`** to process one folder unit at a time (newest mtime first):

| Value | Behaviour |
|-------|-----------|
| `off` (default) | One full-tree discover of `INPUT_PATH` |
| `children` | Alias for `depth:1` |
| `depth:N` | Directories at **relative depth N** under `INPUT_PATH`, one-by-one |

No folder-name conventions required. Depth is relative to `INPUT_PATH`:

| Layout `root / year / month / day` | Setting | Effect |
|------------------------------------|---------|--------|
| Per year | `depth:1` | Usually still large |
| **Per month** | `depth:2` | Recommended for nightly on that layout |
| Per day | `depth:3` | Smaller units |

If `INPUT_PATH` itself has RAW files (not only in subdirs), those are processed first as a non-recursive unit.

Example (whole Event tree, one month at a time):

```env
INPUT_PATH=/mnt/Event
DISCOVER_SPLIT=depth:2
MODE=extract
```

`CRON_STOP` may kill the worker mid-unit; the next run resumes via redis `done` and rediscovers only that unit’s folder (not the entire NAS).

## Cron (host)

`.env` cron keys do **nothing** until applied on the host:

```bash
./scripts/cron-apply.sh
crontab -l | grep jaypeg
```

| Variable | Notes |
|----------|--------|
| `CRON_ENABLE` | `true` installs entries; `false` removes jaypeg crontab lines |
| `CRON_START` | 5-field cron → `job-start.sh` (redis + worker) |
| `CRON_STOP` | 5-field cron → `job-stop.sh` (**worker only**; redis stays up) |

Times follow the **host** timezone (not container `TZ`). Deploy must include `scripts/`. Logs: `result/cron-start.log`, `result/cron-stop.log`.

Manual run: `./scripts/job-start.sh`.

## Configuration

Only keys listed in [`.env.example`](.env.example) are supported.

| Variable | Notes |
|----------|--------|
| `MODE` | `scan` \| `dry-run` \| `extract` \| `develop` |
| `INPUT_PATH` | Path **inside** the container (e.g. `/mnt/Event` or `/mnt/photos`) |
| `LOG_LEVEL` | `verbose` \| `debug` \| `log` \| `warn` \| `error` |
| `TZ` | IANA timezone for container logs (default `UTC`) |
| `INTENT` | `nas` \| `balanced` \| `remote` (concurrency / GPU hint) |
| `HOST_PATH` | Host folder bind-mounted at `/mnt/photos` (compose toggle) |
| `NAS_ADDR` / `NAS_EXPORT` | NFS volume options in compose |
| `DEVELOP_FALLBACK` | `false` = no Darktable on preview miss (**extract** only) |
| `REWRITE` | Regenerate tool-stamped JPGs only (never camera duals) |
| `FORCE_DEVELOP` | Always Darktable on **extract** (skips preview) |
| `ENABLE_GPU` | `true` / `false` / empty (= auto from `INTENT`) |
| `CONCURRENCY` | Empty = autotune; pin worker count for dry-run / extract / develop |
| `DISCOVER_SPLIT` | `off` \| `children` \| `depth:N` — see [Discover split](#discover-split-large-trees) |
| `CRON_*` | See [Cron](#cron-host) |

## FAQ

#### Did you use AI?
Yes. I used Cursor to write the code and this README.

## Feedback
If you have any feedback, please reach out to me at **Work@rioli.net**

## Related
- Stack shape inspired by [Immich](https://immich.app/) (redis + workers, comment-toggle compose)

## Acknowledgements
 - [Readme.so Github](https://github.com/octokatherine/readme.so)
 - [ExifTool](https://exiftool.org/)
 - [Darktable](https://www.darktable.org/)
 - [Immich](https://github.com/immich-app/immich)
 - [Redis](https://redis.io/)
