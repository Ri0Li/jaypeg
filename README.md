# raw2jpg — RAW companion JPEG tool

Batch job that finds RAW files under a path and writes sibling `.JPG` files (camera RAW+JPEG style). Original RAW files are never modified.

Stack (Immich-style): **redis + worker**. One compose file — toggle mounts / GPU / remote worker by **commenting blocks** in [`docker-compose.yml`](docker-compose.yml).

```bash
cp .env.example .env
# edit INPUT_PATH, MODE, INTENT, HOST_PATH or NAS_*
docker compose up
```

Worker exits when the job finishes (`restart: "no"`). Redis can stay up for resume / remote workers.

## Environment reference (`.env`)

Copy [`.env.example`](.env.example) → `.env`. Groups: `run` / `mount` / `size` / `cron` / `advanced`.

Suggested flow: `scan` → check `raw_only` + capacity estimate → `dry-run` → scoped `extract`. Usually only change `MODE` between runs.

### `# run` — what the job does

| Variable | What you set | Notes |
|----------|--------------|--------|
| `INPUT_PATH` | Folder **inside the container** to scan | Photos mount at `/mnt/photos`. Whole mount → `/mnt/photos`. Subfolder → `/mnt/photos/...` |
| `MODE` | `scan` \| `dry-run` \| `extract` | `scan` = count only; `dry-run` = simulate; `extract` = write JPGs |
| `LOG_LEVEL` | `verbose` \| `debug` \| `log` \| `warn` \| `error` | Default `log` |
| `INTENT` | `nas` \| `balanced` \| `remote` | Autotune: gentle / mid / aggressive (+ GPU flag for remote) |

### `# mount` — how photos appear in the container

| Variable | What you set | Notes |
|----------|--------------|--------|
| `HOST_PATH` | Host path for bind mount → `/mnt/photos` | Required for bind mount; set in `.env` |
| `NAS_ADDR` | NFS server address | Only if you uncomment NFS volume in `docker-compose.yml` |
| `NAS_EXPORT` | NFS export path | Must be writable for sibling JPGs |

### `# size` — disk / output quality

| Variable | What you set | Notes |
|----------|--------------|--------|
| `MAX_LONG_EDGE` | Max long-edge pixels (default `2560`) | `0` = no resize |
| `JPEG_QUALITY` | 1–100 (default `85`) | Higher = larger files |
| `DEVELOP_FALLBACK` | `true` / `false` (default `true`) | `false` = no Darktable if preview missing (safer for big NAS runs) |

### `# cron` — scheduled start / stop

| Variable | What you set | Notes |
|----------|--------------|--------|
| `CRON_ENABLE` | `true` / `false` | `true` = install host crontab via script |
| `CRON_START` | 5-field cron in quotes, e.g. `"0 2 * * *"` | `min hour dom month dow` — start job (host system time) |
| `CRON_STOP` | 5-field cron in quotes, e.g. `"0 6 * * *"` | stop **worker only** (redis stays up for resume) |

Apply after editing `.env`:

```bash
./scripts/cron-apply.sh    # CRON_ENABLE=true installs; =false removes
```

Logs: `./result/cron-start.log`, `./result/cron-stop.log`. Manual: `./scripts/job-start.sh` / `./scripts/job-stop.sh`.

### `# advanced`

| Variable | What you set | Notes |
|----------|--------------|--------|
| `REWRITE` | `true` / `false` | Regenerate JPGs that already have this tool’s metadata (`Software` / `CreatorTool`). Never overwrites camera duals. |
| `ENABLE_GPU` | `true` / `false` or empty | Override INTENT GPU; empty = auto from INTENT |

## Extraction behaviour

1. Skip camera duals (sibling JPG without this tool’s stamp). Skip tool companions unless `REWRITE=true`  
2. Try ExifTool embedded `-PreviewImage`, then `-JpgFromRaw`  
3. If that fails → **Darktable CLI** develop (unless `DEVELOP_FALLBACK=false`)  
4. **ImageMagick** resize to `MAX_LONG_EDGE` + `JPEG_QUALITY` (preview and develop)  
5. Stamp metadata (`Software` / `CreatorTool` = `raw2jpg/<version>`) and copy tags from RAW  
6. On total failure: log + Redis failed state, continue next file  

RAW files are never deleted or overwritten.

---

## Capacity and practicality

Companion JPGs add disk next to RAW. **Dual (camera RAW+JPEG) are skipped** and do not grow the archive.

Rough growth ≈ `raw_only × average companion size`. With defaults (`MAX_LONG_EDGE=2560`, `JPEG_QUALITY=85`), plan on **~1 MiB per file** for estimates (`scan` / job start logs this).

| Assumed average companion | 100k raw-only | 200k raw-only | 300k raw-only |
|---------------------------|---------------|---------------|---------------|
| ~1 MiB (after resize) | ~100 GB | ~200 GB | ~300 GB |
| ~2–4 MiB (raw preview, no cap) | ~200–400 GB | ~400–800 GB | ~0.6–1.2 TB |
| Full-res develop ~10–15 MiB | ~1–1.5 TB | ~2–3 TB | ~3–4.5 TB |

**Runtime**

| Path | Rough pace | Full-library scale |
|------|------------|--------------------|
| ExifTool preview only | Mostly NFS I/O; often &lt;1s/file | Days–weeks |
| Preview miss → Darktable | Tens of seconds–minutes/file | Can become **months** if miss rate is high |

**Practical workflow**

1. `MODE=scan` on a small subfolder — read `raw_only` and the GiB estimate  
2. `MODE=dry-run` — see preview vs develop  
3. `MODE=extract` on that scoped path  
4. For big NAS batches: consider `DEVELOP_FALLBACK=false` so missing previews fail fast instead of full develop  
5. Do **not** treat unscoped whole-archive `extract` + high concurrency + develop as the default  

Redis job-state size is negligible. Develop temp files stay in the container temp dir.

---

## Example A — Local path (bind mount)

Default in `docker-compose.yml` (bind line uncommented):

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

Then set `MODE=dry-run` or `MODE=extract` and `up` again.

---

## Example B — Docker NFS / network mount

In `docker-compose.yml`:

1. Comment out the bind line: `# - ${HOST_PATH:?Set HOST_PATH in .env}:/mnt/photos`
2. Uncomment `- photos:/mnt/photos`
3. Uncomment the `photos:` NFS volume block under `volumes:`

```bash
# .env
INPUT_PATH=/mnt/photos
MODE=dry-run
LOG_LEVEL=log
INTENT=remote
NAS_ADDR=192.0.2.10
NAS_EXPORT=/volume1/share/photos
```

```bash
docker compose up
```

Optional GPU: uncomment the `deploy.resources.reservations.devices` block in the same file.

---

## Example C — Path split

Two projects / two `.env` files with different trees:

- A: `INPUT_PATH=/mnt/photos/batch-a` · `COMPOSE_PROJECT_NAME=raw2jpg-a`
- B: `INPUT_PATH=/mnt/photos/batch-b` · `COMPOSE_PROJECT_NAME=raw2jpg-b`

Optional hash shard: `SHARD=0` + `SHARD_COUNT=2`.

---

## Example D — Remote worker (like Immich ML)

**Machine A** (main stack): `docker compose up -d redis` (or full stack).

**Machine B:** copy the same `docker-compose.yml`, then comment as noted in-file:

- Comment out the whole `redis:` service  
- Comment out worker `depends_on`  
- Set `REDIS_URL=redis://<machine-a-lan-ip>:6379/0` and `INTENT=remote` in `.env`  
- Keep bind or NFS photos mount as needed  
- Optionally uncomment GPU  

```bash
docker compose up
```

Do not expose Redis to the public internet.

---

## Identifying tool output

Each written JPG gets Exif/XMP tool tags. Find them with:

```bash
exiftool -if '$Software =~ /raw2jpg/' -q -T -FileName /mnt/photos/...
```

## Scale note

Hundreds of thousands of RAW files is a multi-day job. Prefer scoped `INPUT_PATH` (small subfolders first).

## Layout

```
docker-compose.yml   # only compose file — comment toggles inside
.env.example
Dockerfile
src/
```
