from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidroute.datasets.public_adapters import TauKnowledgeLocalAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a private τ-Knowledge ZIP by member names without extracting it."
    )
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    result = TauKnowledgeLocalAdapter().validate_archive(args.archive)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
