# EvidRoute

**Risk-constrained sequential routing over heterogeneous evidence and interaction sources.**

EvidRoute is an offline-first research system that decides which evidence route to use next
and when to answer, ask for clarification, or abstain. It treats retrieval as a sequential,
budgeted decision problem rather than a single search/no-search toggle.

The default demo is deliberately credential-free. It performs real sparse retrieval,
deterministic dense retrieval, structured graph traversal, episodic-memory lookup, frozen-web
snapshot search, citation verification, counterfactual route evaluation, risk calibration,
and source-shift simulation on the bundled MiniRoute benchmark.

> Research status: engineering prototype and reproducibility scaffold. No state-of-the-art
> claim is made. Public benchmark experiments have not yet been run.

## What is implemented

- Typed route contracts for parametric, memory, BM25, dense, structured, frozen-web, and
  optional live-web evidence.
- One-shot and bounded sequential policies with budget checks, source-health features,
  reason codes, and a positive-value-of-information gate.
- Counterfactual forced-route outcomes, route utility, oracle labels, and regret.
- CPU-friendly learned potential-outcome routing and transparent baselines.
- Selective-risk calibration with one-sided confidence bounds and shift-aware fallback.
- Two frozen snapshots, deterministic corruption manifests, drift detection, and recalibration.
- FastAPI endpoints, SQLite trace storage, JSON trace export, and a React/TypeScript research UI.
- Unit, integration, failure-injection, API, and browser-oriented tests.
- Docker, CI, paper skeleton, model card, data statement, and reproducibility reports.

## Quick start

### Windows PowerShell

```powershell
./scripts/setup.ps1
./scripts/test.ps1
./scripts/smoke.ps1
./scripts/demo.ps1
```

### POSIX / WSL

```bash
make setup
make test
make smoke
make demo
```

The API runs at `http://localhost:8000` and the web application at
`http://localhost:5173`.

## Reproduce MiniRoute

```bash
python -m evidroute.cli reproduce-mini --output artifacts/reproduce-mini
```

This command rebuilds deterministic indices, generates forced-route outcomes, trains the CPU
router, calibrates the risk controller, evaluates fixed and adaptive policies, runs the shift
suite, and generates paper-style Markdown/CSV/SVG assets from raw predictions.

## Private benchmark policy

The optional τ-Knowledge adapter reads a user-supplied archive path at runtime. Private
documents, tasks, policies, or generated traces are excluded from version control, Docker
images, CI, and public artifacts. See [the data statement](reports/data_statement.md).

## Repository map

```text
apps/api          FastAPI entry point
apps/web          React + TypeScript + Vite application
src/evidroute     Routing, evidence, risk, evaluation, security, and traces
data/mini_route   Redistributable deterministic benchmark
configs           Validated smoke, router, shift, and paper configurations
scripts           Setup, smoke, evaluation, and asset generation commands
tests             Unit, integration, failure, API, and browser tests
paper             LaTeX skeleton and generated tables/figures
reports           Model card, data statement, ethics, and reproducibility
```

## Scientific scope

The strongest currently defensible claim is narrow: the repository provides a complete,
auditable testbed for studying risk-constrained sequential evidence routing under controlled
source shift. Claims about superiority on public benchmarks require the pre-registered
experiments in `configs/paper/` and are intentionally marked unrun.

## Citation

See [`CITATION.cff`](CITATION.cff). Related-work entries were verified against the supplied
ACL 2025, EMNLP 2025, NeurIPS 2025, and ICML 2026 manuscripts.
