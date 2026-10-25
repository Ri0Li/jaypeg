#!/usr/bin/env bash
# Delete companion JPGs stamped by this tool (Software contains raw2jpg).
# Never deletes camera duals without the tool stamp.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export ROOT
python3 << 'PY'
import os
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT"])
env: dict[str, str] = {}
env_path = root / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")

host = Path(env.get("HOST_PATH", ""))
if not host.is_dir():
    raise SystemExit(f"HOST_PATH not a directory: {host}")

tool = "raw2jpg"
deleted = kept = 0
jpgs = [p for p in host.rglob("*") if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}]


def software_blob(jpg: Path) -> str:
    if subprocess.run(["which", "exiftool"], capture_output=True).returncode == 0:
        proc = subprocess.run(
            ["exiftool", "-s3", "-Software", "-ProcessingSoftware", "-XMP-xmp:CreatorTool", str(jpg)],
            capture_output=True,
            text=True,
        )
        return (proc.stdout or "") + (proc.stderr or "")
    rel = jpg.relative_to(host).as_posix()
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "exiftool",
            "-v", f"{host}:/photos:ro", "raw2jpg-worker",
            "-s3", "-Software", "-ProcessingSoftware", "-XMP-xmp:CreatorTool", f"/photos/{rel}",
        ],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "") + (proc.stderr or "")


for jpg in jpgs:
    blob = software_blob(jpg)
    if tool in blob:
        jpg.unlink()
        deleted += 1
        print(f"deleted {jpg}")
    else:
        kept += 1

print(f"cleanup done: deleted={deleted} kept_other={kept} tool={tool}")
PY
