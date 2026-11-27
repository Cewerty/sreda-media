#!/usr/bin/env python3
"""Compute a canonical digest of a directory tree.

The digest is stable across mtime, ordering and filesystem metadata that does
not affect served bytes. Symlinks are recorded by target, not by dereferenced
content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDE = {
    ".git",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="directory to digest")
    parser.add_argument(
        "--include",
        type=Path,
        help="file with one relative path per line; only these paths are hashed",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="optional path for a per-entry JSON manifest",
    )
    return parser.parse_args(argv)


def include_list(path: Path | None, root: Path) -> set[str] | None:
    """Read an explicit include list of canonical relative paths."""
    if path is None:
        return None
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        rel = value.replace("\\", "/").lstrip("/")
        if (root / rel).exists():
            entries.add(rel)
    return entries


def entries(root: Path, included: set[str] | None) -> list[tuple[str, str, str]]:
    """Return sorted (relative path, kind, payload) triples."""
    result: list[tuple[str, str, str]] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("./"):
            rel = rel[2:]
        if any(part in DEFAULT_EXCLUDE for part in path.relative_to(root).parts):
            continue
        if included is not None and rel not in included:
            continue
        if path.is_symlink():
            result.append((rel, "symlink", path.readlink().as_posix()))
            continue
        if not path.is_file():
            continue
        mode = "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result.append((rel, mode, digest))
    return sorted(result)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"FAIL: not a directory: {root}", file=sys.stderr)
        return 1
    included = include_list(args.include, root)
    collected = entries(root, included)
    if not collected:
        print("FAIL: no files selected for digest", file=sys.stderr)
        return 1
    hasher = hashlib.sha256()
    for rel, kind, payload in collected:
        line = f"{kind} {rel} {payload}\n".encode("utf-8")
        hasher.update(line)
    digest = hasher.hexdigest()
    print(f"sha256:{digest}")
    if args.manifest:
        manifest: dict[str, Any] = {
            "algorithm": "canonical-tree-v1",
            "root": str(root),
            "digest": f"sha256:{digest}",
            "entries": [
                {"path": rel, "kind": kind, "value": payload}
                for rel, kind, payload in collected
            ],
        }
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
