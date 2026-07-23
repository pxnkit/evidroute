# Reproducibility

The credential-free MiniRoute path is the executable reference experiment.

```bash
python -m evidroute.cli reproduce-mini --output artifacts/reproduce-mini --seed 17
```

The run writes forced-route outcomes, a learned router checkpoint, calibration data, raw
predictions, aggregate metrics, corruption manifests, drift results, CSV/SVG report assets, and
`run_manifest.json`.

The manifest records:

- Python, platform, and relevant package versions;
- random seed and validated engine configuration;
- configuration SHA-256;
- hashes of every bundled MiniRoute input;
- Git commit and worktree status, when available;
- snapshot, index, and schema versions.

Determinism applies to the bundled CPU routes and MiniRoute input. Wall-clock timings, operating
system scheduling, dependency solver output, and floating-point behavior across different
architectures may vary. A public benchmark run is a separate experiment and must retain its
license, download provenance, original split, preprocessing hash, and evaluation command.

## Scientific claim boundary

The generated smoke report demonstrates that the pipeline executes and emits auditable
artifacts. It is not evidence that EvidRoute outperforms published systems. The repository does
not report a public benchmark result until the corresponding run exists.
