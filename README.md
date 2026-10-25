# raw2jpg — RAW companion JPEG tool

Batch job that finds RAW files under a path and writes sibling `.JPG` files (camera RAW+JPEG style). Original RAW files are never modified.

Stack (Immich-style): **redis + worker**. One compose file — toggle mounts / GPU / remote worker by **commenting blocks** in [`docker-compose.yml`](docker-compose.yml).

```bash
cp .env.example .env
# edit INPUT_PATH, MODE, INTENT, HOST_PATH or NAS_*
docker compose up
```

Worker exits when the job finishes (`restart: "no"`). Redis data persists in the `redis-data` volume for resume.

## Environment reference (`.env`)

Copy [`.env.example`](.env.example) → `.env`. **Only keys in `.env.example` are supported** — there are no hidden options.

Suggested flow: `scan` → read `./result/LATEST.md` → `dry-run` → scoped `extract`. Usually only change `MODE` between runs.

### `# run` — what the job does

| Variable | What you set | Notes |
|----------|--------------|--------|
| `INPUT_PATH` | Folder **inside the container** to scan | Photos mount at `/mnt/photos` |
| `MODE` | `scan` \| `dry-run` \| `extract` | `scan` = count + report; `dry-run` = simulate; `extract` = write JPGs |
| `LOG_LEVEL` | `verbose` \| `debug` \| `log` \| `warn` \| `error` | Default `log` |
| `INTENT` | `nas` \| `balanced` \| `remote` | Autotune concurrency (+ GPU flag for remote) |

### `# mount` — how photos appear in the container

| Variable | What you set | Notes |
|----------|--------------|--------|
| `HOST_PATH` | Host path for bind mount → `/mnt/photos` | Required for bind mount |
| `NAS_ADDR` | NFS server address | Only if you uncomment NFS volume in compose |
| `NAS_EXPORT` | NFS export path | Must be writable for sibling JPGs |

### `# behaviour`

| Variable | What you set | Notes |
|----------|--------------|--------|
| `DEVELOP_FALLBACK` | `true` / `false` | `false` = no Darktable if embed preview missing |

Output size is fixed in code: **no resize / no recompress** (native embed, or full-res develop with auto-orient).

### `# cron` — scheduled start / stop

| Variable | What you set | Notes |
|----------|--------------|--------|
| `CRON_ENABLE` | `true` / `false` | `true` = install host crontab via script |
| `CRON_START` | 5-field cron in quotes, e.g. `"0 2 * * *"` | start job (host system time) |
| `CRON_STOP` | 5-field cron in quotes, e.g. `"0 6 * * *"` | stop **worker only** |

```bash
./scripts/cron-apply.sh    # CRON_ENABLE=true installs; =false removes
```

Logs: `./result/cron-start.log`, `./result/cron-stop.log`. Manual: `./scripts/job-start.sh` / `./scripts/job-stop.sh`.

### `# advanced`

| Variable | What you set | Notes |
|----------|--------------|--------|
| `REWRITE` | `true` / `false` | Regenerate JPGs stamped by this tool. Never overwrites camera duals. |
| `FORCE_DEVELOP` | `true` / `false` | Skip embed preview; always full-res darktable (concurrency forced to 1). |
| `ENABLE_GPU` | `true` / `false` or empty | Override INTENT GPU; empty = auto from INTENT |

## Extraction behaviour

1. Skip camera duals (sibling JPG without this tool’s stamp). Skip tool companions unless `REWRITE=true`
2. Try ExifTool embedded `-PreviewImage`, then `-JpgFromRaw` (kept as-is, no shrink)
3. If that fails → **Darktable CLI** full-res develop (unless `DEVELOP_FALLBACK=false`), then **auto-orient** so portrait stays upright
4. Stamp metadata (`Software` / `CreatorTool` = `raw2jpg/<version>`) and copy tags from RAW
5. On total failure: log + Redis failed state, continue next file

RAW files are never deleted or overwritten.

Scan / dry-run write markdown under `./result/` (`LATEST.md`, `jobs/`, `HISTORY.md`).

---

## Capacity and practicality

Companion JPGs add disk next to RAW. **Camera duals are skipped**. Tool companions are skipped unless `REWRITE=true`.

Rough growth ≈ `raw_only × average companion size` (native embed often a few MiB; full develop often ~15–25 MiB).

| Path | Rough pace | Full-library scale |
|------|------------|--------------------|
| ExifTool preview only | Mostly I/O; often &lt;1s/file | Days–weeks |
| Preview miss → Darktable | Seconds–minutes/file | Can become **months** if miss rate is high |

**Practical workflow**

1. `MODE=scan` — read `./result/LATEST.md`
2. `MODE=dry-run`
3. `MODE=extract` on a scoped `INPUT_PATH`
4. For big NAS batches: consider `DEVELOP_FALLBACK=false` so missing previews fail fast
5. Do **not** treat unscoped whole-archive `extract` + develop as the default

---

## Gotchas (from testing)

1. **Embed ≠ full RAW pixels** — camera preview is often ~1600px; full sensor only via develop.
2. **Darktable uses isolated config** — shared config breaks concurrent develops.
3. **`job-start.sh` / `compose up --abort-on-container-exit`** stops redis when the worker exits; resume uses the redis **volume**, not a live process.
4. **Scan splits** `camera_dual` / `tool_companion` / `raw_only` — after extract, tool companions are not counted as camera duals.
5. Wipe tool JPGs before A/B tests: `./scripts/cleanup-tool-jpgs.sh` (metadata `Software` contains `raw2jpg`; camera duals kept).

---

## Example A — Local path (bind mount)

```bash
# .env
INPUT_PATH=/mnt/photos
MODE=scan
LOG_LEVEL=log
INTENT=balanced
HOST_PATH=/path/to/photos
```

```bash
docker compose up
```

---

## Example B — Docker NFS / network mount

In `docker-compose.yml`:

1. Comment out the bind line: `# - ${HOST_PATH:?Set HOST_PATH in .env}:/mnt/photos`
2. Uncomment `- photos:/mnt/photos`
3. Uncomment the `photos:` NFS volume block under `volumes:`

```bash
INPUT_PATH=/mnt/photos
MODE=dry-run
INTENT=remote
NAS_ADDR=192.0.2.10
NAS_EXPORT=/volume1/share/photos
```

Optional GPU: uncomment the `deploy.resources.reservations.devices` block.

---

## Example C — Path split

Two projects / two `.env` files with different trees:

- A: `INPUT_PATH=/mnt/photos/batch-a` · `COMPOSE_PROJECT_NAME=raw2jpg-a`
- B: `INPUT_PATH=/mnt/photos/batch-b` · `COMPOSE_PROJECT_NAME=raw2jpg-b`

---

## Example D — Remote worker (like Immich ML)

**Machine A** (main stack): `docker compose up -d redis` (or full stack). Publish Redis on LAN only.

**Machine B:** same compose file, then:

- Comment out the whole `redis:` service
- Comment out worker `depends_on`
- Change worker `REDIS_URL` in compose to `redis://<machine-a-lan-ip>:6379/0`
- Set `INTENT=remote` in `.env`
- Keep photos mount; optionally uncomment GPU

Do not expose Redis to the public internet.

---

## Identifying / cleaning tool output

```bash
exiftool -if '$Software =~ /raw2jpg/' -q -T -FileName /path/to/photos
./scripts/cleanup-tool-jpgs.sh   # needs HOST_PATH in .env
```

## Scale note

Hundreds of thousands of RAW files is a multi-day job. Prefer scoped `INPUT_PATH` (small subfolders first).

## Layout

```
docker-compose.yml   # only compose file — comment toggles inside
.env.example         # only supported env keys
Dockerfile
scripts/
src/
result/              # scan/dry-run reports (gitignored)
```
