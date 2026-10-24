from __future__ import annotations

RAW_EXTENSIONS = frozenset(
    {
        ".cr3",
        ".cr2",
        ".nef",
        ".nrw",
        ".arw",
        ".srf",
        ".sr2",
        ".dng",
        ".raf",
        ".orf",
        ".rw2",
        ".pef",
        ".ptx",
        ".srw",
        ".raw",
        ".rwl",
        ".3fr",
        ".fff",
        ".iiq",
        ".eip",
    }
)

SIBLING_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".webp",
        ".tif",
        ".tiff",
        ".png",
        ".heic",
        ".heif",
    }
)


def is_raw(path_name: str) -> bool:
    return path_name.lower().endswith(tuple(RAW_EXTENSIONS))


def iter_sibling_non_raw(raw_path):
    from pathlib import Path

    p = Path(raw_path)
    stem = p.stem
    parent = p.parent
    for child in parent.iterdir():
        if not child.is_file():
            continue
        if child.stem != stem:
            continue
        if child.suffix.lower() in SIBLING_EXTENSIONS:
            yield child


def has_sibling_non_raw(raw_path) -> bool:
    return next(iter_sibling_non_raw(raw_path), None) is not None


def sibling_stamped_by_tool(raw_path, tool_name: str) -> bool:
    """True if a sibling image was written by this tool (Software / CreatorTool)."""
    import subprocess

    for sibling in iter_sibling_non_raw(raw_path):
        try:
            proc = subprocess.run(
                [
                    "exiftool",
                    "-s3",
                    "-Software",
                    "-ProcessingSoftware",
                    "-XMP-xmp:CreatorTool",
                    str(sibling),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        blob = (proc.stdout or "") + (proc.stderr or "")
        if tool_name and tool_name in blob:
            return True
    return False


def companion_jpg_path(raw_path, output_ext: str = ".JPG"):
    from pathlib import Path

    p = Path(raw_path)
    return p.with_name(p.stem + output_ext)
