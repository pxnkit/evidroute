# Architecture

EvidRoute models evidence acquisition as a bounded sequential decision process. At every step,
the router may acquire from one feasible source or stop with `ANSWER`, `ASK_USER`, or
`ABSTAIN`.

```text
Query + budget + risk target + snapshot
                  |
            decision features
                  |
       probes + health + policy scorer
                  |
       conservative utility ranking
                  |
     acquire one typed evidence bundle
                  |
  normalize -> deduplicate -> detect conflict
                  |
       answer + citation + risk check
             |             |
           stop       acquire next route
```

## Components

| Component | Responsibility |
| --- | --- |
| `models.py` | Strict schemas for budgets, evidence, candidates, decisions, and traces |
| `routes/` | Stable adapter contract and seven route implementations |
| `routing/policy.py` | Decision-time scoring, feasibility, value of information, stop rule |
| `routing/learned.py` | CPU potential-outcome utility model trained from forced routes |
| `synthesis/` | Evidence-only answer selection, deduplication, conflict policy |
| `risk/` | One-sided selective-risk bounds and source-shift detection |
| `counterfactual/` | Forced-route potential outcomes, oracle, and atomic regret |
| `observability/` | Local SQLite traces, feedback, canonical JSON export |
| `api.py` | FastAPI transport, validation, upload guardrails, SSE |
| `apps/web` | React console for decisions, evidence, conflicts, budgets, and replay |

## Route contract

Each route exposes `availability`, `estimate`, `probe`, `acquire`, `health`, and `close`.
Acquisition returns a normalized `EvidenceBundle` with typed failure codes. Probes are included
in the decision trace and treated as costed observations; no hidden retrieval label is used at
decision time.

## Offline implementation

BM25 is implemented from corpus statistics. Dense retrieval uses deterministic signed feature
hashing, making the smoke path CPU-only and reproducible. Structured retrieval performs bounded
graph traversal with source-document provenance. Frozen web uses versioned snapshots. The live
web adapter is deliberately unavailable in the default configuration.

## Invariants

1. An answer in verified mode must cite normalized, safe evidence.
2. Every route call spends its estimate from a multidimensional budget.
3. Source failure, privacy denial, and malformed/no-result states are typed.
4. Trace export includes the configuration hash, source versions, model versions, and timing.
5. Shift detection invalidates the calibration guarantee instead of silently reusing it.
