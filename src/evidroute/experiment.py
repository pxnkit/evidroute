from __future__ import annotations

import csv
import json
import os
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

from evidroute.config import EngineConfig
from evidroute.counterfactual import CounterfactualRunner
from evidroute.datasets import CorpusStore
from evidroute.evaluation.metrics import aggregate_outcomes, bootstrap_mean_interval
from evidroute.models import CounterfactualOutcome, MiniRouteCase, RouteName
from evidroute.reproducibility import write_manifest
from evidroute.risk import SelectiveRiskController
from evidroute.routing.learned import PotentialOutcomeRouter
from evidroute.shifts import ShiftSuite

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
warnings.filterwarnings(
    "ignore",
    message="Could not find the number of physical cores",
    module=r"joblib\.externals\.loky\.backend\.context",
)


class MiniExperiment:
    def __init__(self, output_dir: Path, seed: int = 17) -> None:
        self.output_dir = output_dir
        self.seed = seed
        self.config = EngineConfig()
        self.corpus = CorpusStore()
        self.counterfactual = CounterfactualRunner(
            corpus=self.corpus, config=self.config, seed=seed
        )

    def run(self) -> dict[str, object]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        outcomes = self.counterfactual.run()
        CounterfactualRunner.save(outcomes, self.output_dir / "counterfactual_outcomes.jsonl")
        oracle = CounterfactualRunner.oracle(outcomes)

        training = [outcome for outcome in outcomes if outcome.split in {"train", "calibration"}]
        router = PotentialOutcomeRouter().fit(training, self.corpus)
        router.save(self.output_dir / "models" / "potential_outcome_router.pkl")

        calibration_rows = [outcome for outcome in training if outcome.feasible]
        calibration_scores = [
            0.95 if outcome.supported and outcome.correct else 0.15 for outcome in calibration_rows
        ]
        calibration_losses = [
            int(not (outcome.supported and outcome.correct)) for outcome in calibration_rows
        ]
        calibration = SelectiveRiskController(self.config.confidence_level).fit(
            calibration_scores,
            calibration_losses,
            risk_target=self.config.default_risk_target,
            snapshot_id="t1",
        )
        calibration_path = self.output_dir / "calibration.json"
        calibration_path.write_text(json.dumps(calibration.as_dict(), indent=2), encoding="utf-8")

        selected: dict[str, CounterfactualOutcome] = {}
        cases = {case.case_id: case for case in self.corpus.cases}
        by_case: dict[str, list[CounterfactualOutcome]] = defaultdict(list)
        for outcome in outcomes:
            by_case[outcome.case_id].append(outcome)
        for case_id, case_outcomes in by_case.items():
            case = cases[case_id]
            feasible_routes = [row.route for row in case_outcomes if row.feasible]
            if not feasible_routes:
                continue
            predictions = router.predict(
                query=case.question,
                task_family=case.task_family,
                snapshot_id=case.snapshot_id,
                feasible_routes=feasible_routes,
            )
            chosen_route = predictions[0].route
            selected[case_id] = next(row for row in case_outcomes if row.route is chosen_route)

        selected_rows = [
            row.model_dump(mode="json")
            for case_id, row in selected.items()
            if cases[case_id].split in {"test", "shifted_test"}
        ]
        fixed_metrics = {}
        for route in RouteName:
            route_rows = [
                outcome.model_dump(mode="json")
                for outcome in outcomes
                if outcome.route is route and outcome.split in {"test", "shifted_test"}
            ]
            fixed_metrics[route.value] = aggregate_outcomes(route_rows)
        learned_metrics = aggregate_outcomes(selected_rows)
        oracle_rows = [
            row.model_dump(mode="json")
            for case_id, row in oracle.items()
            if cases[case_id].split in {"test", "shifted_test"}
        ]
        oracle_metrics = aggregate_outcomes(oracle_rows)
        regret = CounterfactualRunner.regret(selected, oracle)
        regret_interval = bootstrap_mean_interval(regret.values(), seed=self.seed)

        shift_result = ShiftSuite.write(self.output_dir / "shifts")
        metrics = {
            "scope": "MiniRoute synthetic benchmark only",
            "seed": self.seed,
            "learned_router": learned_metrics,
            "fixed_routes": fixed_metrics,
            "counterfactual_oracle": oracle_metrics,
            "route_regret": {
                "mean": regret_interval[0],
                "ci95_low": regret_interval[1],
                "ci95_high": regret_interval[2],
                "count": len(regret),
            },
            "risk_calibration": calibration.as_dict(),
            "shift_suite": shift_result,
        }
        (self.output_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        self._write_predictions(selected, oracle, cases)
        self._write_report(metrics)
        self._write_assets(metrics)
        write_manifest(self.output_dir / "run_manifest.json", self.config, self.seed)
        return metrics

    def _write_predictions(
        self,
        selected: dict[str, CounterfactualOutcome],
        oracle: dict[str, CounterfactualOutcome],
        cases: dict[str, MiniRouteCase],
    ) -> None:
        rows = []
        for case_id, outcome in selected.items():
            oracle_row = oracle[case_id]
            rows.append(
                {
                    "case_id": case_id,
                    "split": cases[case_id].split,
                    "selected_route": outcome.route.value,
                    "selected_utility": outcome.utility,
                    "oracle_route": oracle_row.route.value,
                    "oracle_utility": oracle_row.utility,
                    "regret": oracle_row.utility - outcome.utility,
                    "supported": outcome.supported,
                    "correct": outcome.correct,
                    "cost": outcome.monetary_cost,
                    "latency_ms": outcome.latency_ms,
                }
            )
        path = self.output_dir / "predictions.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["case_id"])
            writer.writeheader()
            writer.writerows(rows)

    def _write_report(self, metrics: dict[str, Any]) -> None:
        learned = metrics["learned_router"]
        oracle = metrics["counterfactual_oracle"]
        regret = metrics["route_regret"]
        calibration = metrics["risk_calibration"]
        lines = [
            "# EvidRoute MiniRoute smoke report",
            "",
            "> Scope: executed synthetic MiniRoute benchmark only. Public benchmark experiments are unrun.",
            "",
            "## Learned router",
            "",
            f"- Supported accuracy: {learned.get('supported_accuracy', 0):.3f}",
            f"- Exact match: {learned.get('exact_match', 0):.3f}",
            f"- Mean utility: {learned.get('mean_utility', 0):.3f}",
            f"- Mean cost: {learned.get('mean_cost', 0):.4f}",
            "",
            "## Counterfactual oracle",
            "",
            f"- Supported accuracy: {oracle.get('supported_accuracy', 0):.3f}",
            f"- Mean utility: {oracle.get('mean_utility', 0):.3f}",
            "",
            "## Routing and risk",
            "",
            f"- Mean atomic route regret: {regret['mean']:.3f} "
            f"(95% bootstrap CI {regret['ci95_low']:.3f}, {regret['ci95_high']:.3f})",
            f"- Calibrated threshold: {calibration['threshold']:.3f}",
            f"- Selective-risk upper bound: {calibration['upper_bound']:.3f}",
            f"- Calibration coverage: {calibration['coverage']:.3f}",
            "",
            "## Interpretation",
            "",
            "These values validate pipeline behavior and auditability on deterministic synthetic data. "
            "They do not establish the paper's central empirical claim on external datasets.",
        ]
        (self.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_assets(self, metrics: dict[str, Any]) -> None:
        figures = self.output_dir / "figures"
        tables = self.output_dir / "tables"
        figures.mkdir(parents=True, exist_ok=True)
        tables.mkdir(parents=True, exist_ok=True)
        fixed = metrics["fixed_routes"]
        rows = [
            (route, values.get("supported_accuracy", 0.0), values.get("mean_cost", 0.0))
            for route, values in fixed.items()
            if values
        ]
        with (tables / "fixed_route_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["route", "supported_accuracy", "mean_cost"])
            writer.writerows(rows)
        width, height = 760, 380
        max_cost = max((row[2] for row in rows), default=1.0) or 1.0
        circles = []
        labels = []
        for index, (route, quality, cost) in enumerate(rows):
            x = 90 + (cost / max_cost) * 590
            y = 310 - quality * 240
            color = ["#39d98a", "#7c5cff", "#ffb454", "#44b8f3"][index % 4]
            circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}"/>')
            labels.append(
                f'<text x="{x + 10:.1f}" y="{y + 4:.1f}" fill="#d9e2ef" font-size="12">{route}</text>'
            )
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" rx="18" fill="#0b1020"/>
<text x="36" y="42" fill="#f7f9fc" font-size="20" font-family="system-ui">MiniRoute quality-cost map</text>
<line x1="70" y1="320" x2="710" y2="320" stroke="#64748b"/>
<line x1="70" y1="70" x2="70" y2="320" stroke="#64748b"/>
<text x="315" y="360" fill="#94a3b8" font-size="13">Mean route cost</text>
<text x="18" y="210" transform="rotate(-90 18 210)" fill="#94a3b8" font-size="13">Supported accuracy</text>
{"".join(circles)}
{"".join(labels)}
</svg>"""
        (figures / "quality_cost.svg").write_text(svg, encoding="utf-8")
