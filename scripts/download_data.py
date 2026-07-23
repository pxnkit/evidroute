from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs" / "datasets" / "public.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def datasets() -> list[dict[str, Any]]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return list(payload["datasets"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List or register user-downloaded public benchmark files."
    )
    parser.add_argument(
        "--register",
        type=Path,
        help="record hashes for files under data/downloads",
    )
    args = parser.parse_args()

    print("Public datasets are not downloaded automatically. Review the current license first:")
    for row in datasets():
        expected = ROOT / row["expected_path"]
        status = "present" if expected.exists() else "missing"
        print(f"- {row['id']}: {row['homepage']} ({status}: {row['expected_path']})")

    if args.register is None:
        return 0
    root = args.register.resolve()
    allowed = (ROOT / "data" / "downloads").resolve()
    if root != allowed and allowed not in root.parents:
        raise SystemExit("--register must point inside data/downloads")
    if not root.exists():
        raise SystemExit(f"path does not exist: {root}")
    files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
    result = {
        "root": str(root),
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    output = ROOT / "artifacts" / "dataset_registration.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
