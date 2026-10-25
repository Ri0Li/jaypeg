# jaypeg
**jaypeg** (sounds like *JPEG*) finds RAW files under a path and writes sibling `.JPG` companions — camera RAW+JPEG style. Original RAW files are never modified. This repository includes the Docker Compose stack, worker image, and host cron helpers.

Companions are stamped `jaypeg/<version>` in `Software` / `CreatorTool`.

<!-- ## Demo -->

## To Get Started

### Requirements
To run this project, you will need the following:

* **Docker Compose:** redis + worker — see [`docker-compose.yml`](docker-compose.yml) (comment toggles for bind mount / NFS / GPU / remote worker).
* **Photos mount:** a host path (`HOST_PATH`) or NFS export that is writable for `extract`.
* **Config:** copy [`.env.example`](.env.example) → `.env`. **Only keys in `.env.example` are supported.**
* **Worker image (optional pull):** [`ghcr.io/ri0li/jaypeg`](https://github.com/Ri0Li/jaypeg/pkgs/container/jaypeg) (`:latest` on `main`, also `v*` tags; `linux/amd64` + `linux/arm64`).

> **Note:** Prefer `MODE=scan` → read `./result/LATEST.md` → `dry-run` → scoped `extract`. Use `MODE=develop` only for RAWs **without** an embedded preview (Darktable). Unscoped Darktable can take a very long time and use a lot of disk!

### Software
1. Clone this repo and `cp .env.example .env`. Set `HOST_PATH` (or NFS vars), `MODE`, and `INTENT`.
2. `docker compose pull` (or `docker compose build worker` for a local image).
3. `docker compose up` — worker exits when the job finishes; redis data stays in the volume for resume.
4. After `scan` / `dry-run`, check `./result/LATEST.md`. Set `MODE=extract` on a small `INPUT_PATH` when it looks sane.
5. ???
6. Profit

Useful extras: `./scripts/cron-apply.sh`, `./scripts/job-start.sh` / `job-stop.sh`, `./scripts/cleanup-tool-jpgs.sh`.

### What extract does
1. Skip camera duals (sibling JPG without this tool’s stamp). Skip tool companions unless `REWRITE=true`.
2. Try ExifTool embedded preview (`-PreviewImage`, then `-JpgFromRaw`).
3. If that fails → Darktable full-res develop (unless `DEVELOP_FALLBACK=false`), then auto-orient.
4. Stamp metadata and copy tags from the RAW. RAW files are never overwritten.

### What develop does
1. Same sibling / rewrite skips as extract.
2. If the RAW **has** an embedded preview → **skip** (leave it alone).
3. If **no** embed → Darktable full-res JPEG + auto-orient + stamp.
4. Throughput autotune: **GPU** (`ENABLE_GPU` / `INTENT=remote`) → concurrency `1` so one job saturates the card; **CPU-only** → parallel workers sized by CPU/RAM (with `OMP_NUM_THREADS` capped per worker). Pin with `CONCURRENCY=` anytime.

### `.env` cheat sheet

| Variable | Notes |
|----------|--------|
| `MODE` | `scan` \| `dry-run` \| `extract` \| `develop` |
| `INTENT` | `nas` \| `balanced` \| `remote` (concurrency / GPU hint) |
| `HOST_PATH` | Host folder bind-mounted at `/mnt/photos` |
| `DEVELOP_FALLBACK` | `false` = no Darktable on preview miss (**extract** only) |
| `REWRITE` | Regenerate tool-stamped JPGs only (never camera duals) |
| `FORCE_DEVELOP` | Always Darktable on **extract** (skips preview); concurrency follows GPU/CPU rules above |
| `ENABLE_GPU` | `true` / `false` / empty (= auto from `INTENT`) |
| `CONCURRENCY` | Empty = autotune; set to pin workers (`dry-run` / `extract` / `develop`) |

Cron: `CRON_ENABLE`, `CRON_START`, `CRON_STOP` (stop kills **worker only**).

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
