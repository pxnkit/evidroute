# MiniRoute smoke result

> Executed 2026-07-23 on the bundled synthetic MiniRoute benchmark with seed 17. Public
> benchmark experiments remain unrun.

## Learned route policy

| Metric | Value |
| --- | ---: |
| Cases | 14 |
| Exact match | 0.286 |
| Token F1 | 0.300 |
| Supported accuracy | 0.286 |
| Mean utility | 0.444 |
| Mean route cost | 0.0136 |
| Median route latency | 18 ms |

## Counterfactual comparison

| Metric | Learned policy | Oracle |
| --- | ---: | ---: |
| Supported accuracy | 0.286 | 0.429 |
| Mean utility | 0.444 | 0.609 |

Mean atomic route regret was 0.318, with a 95% seeded bootstrap interval of
[0.144, 0.516] over 23 cases with a feasible oracle and selected route.

## Selective risk

- Target risk: 0.250
- Selected confidence threshold: 0.950
- Empirical accepted-set risk: 0.000
- One-sided upper bound: 0.197
- Coverage: 0.297
- Calibration examples: 37
- Loss: unsupported or incorrect

The deterministic shift suite detected score-distribution, source-error-rate, and mean-score
shift. The controller therefore reported `unavailable_under_shift` rather than carrying the
calibration status across the shift.

## Reproducibility

- Configuration SHA-256:
  `9fb232654fbcffa4a91912e87f7e2d32d2d43a095bc1fca0663fb04532a83ed6`
- Command:
  `python -m evidroute.cli smoke --output artifacts/final-smoke --seed 17`
- Full raw predictions, counterfactual outcomes, calibration, figures, tables, model checkpoint,
  and run manifest are regenerated under `artifacts/final-smoke`.

These numbers validate execution, observability, and artifact generation on a small synthetic
fixture. They do not establish superiority, external validity, or a paper-level empirical claim.
