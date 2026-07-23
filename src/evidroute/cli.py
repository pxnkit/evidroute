from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from evidroute.config import project_root
from evidroute.engine import EvidRouteEngine
from evidroute.experiment import MiniExperiment
from evidroute.models import Budget, QueryRequest, VerificationMode


def _query(args: argparse.Namespace) -> int:
    response = EvidRouteEngine().query(
        QueryRequest(
            query=args.question,
            mode=VerificationMode(args.mode),
            risk_target=args.risk,
            snapshot_id=args.snapshot,
            budget=Budget(route_calls=args.route_calls),
        )
    )
    print(json.dumps(response.model_dump(mode="json"), indent=2))
    return 0


def _smoke(args: argparse.Namespace) -> int:
    metrics = MiniExperiment(Path(args.output), seed=args.seed).run()
    print(json.dumps(metrics, indent=2))
    return 0


def _paper_smoke(_: argparse.Namespace) -> int:
    downloads = project_root() / "data" / "downloads"
    if not downloads.exists() or not any(downloads.iterdir()):
        print(
            "Public benchmark data is not installed. Run scripts/download_data.py, "
            "review each dataset license, and place approved files under data/downloads/. "
            "MiniRoute remains fully runnable."
        )
        return 0
    print("Public benchmark files detected; use configs/datasets/*.json for preprocessing.")
    return 0


def _api(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "evidroute.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(project_root()),
    )
    return 0


def _demo(_: argparse.Namespace) -> int:
    root = project_root()
    environment = os.environ.copy()
    api = subprocess.Popen(
        [sys.executable, "-m", "evidroute.cli", "api"],
        cwd=root,
        env=environment,
    )
    try:
        return subprocess.call(["pnpm", "dev"], cwd=root / "apps" / "web", env=environment)
    finally:
        api.terminate()
        api.wait(timeout=10)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidroute")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query = subparsers.add_parser("query", help="run one offline query")
    query.add_argument("question")
    query.add_argument("--mode", choices=["verified", "best_effort"], default="verified")
    query.add_argument("--risk", type=float, default=0.25)
    query.add_argument("--snapshot", choices=["t0", "t1"], default="t1")
    query.add_argument("--route-calls", type=int, default=3)
    query.set_defaults(handler=_query)

    for name in ("smoke", "reproduce-mini"):
        smoke = subparsers.add_parser(name, help="run the MiniRoute pipeline")
        smoke.add_argument("--output", default=f"artifacts/{name}")
        smoke.add_argument("--seed", type=int, default=17)
        smoke.set_defaults(handler=_smoke)

    paper = subparsers.add_parser("paper-smoke")
    paper.set_defaults(handler=_paper_smoke)

    api = subparsers.add_parser("api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(handler=_api)

    demo = subparsers.add_parser("demo")
    demo.set_defaults(handler=_demo)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
