# Data statement

## MiniRoute

`data/mini_route` is a small synthetic dataset created for this repository. It contains fictional
entities, deterministic QA cases, memories, source conflicts, temporal snapshots, and failure
scenarios. It contains no intended real personal data. The repository MIT license covers this
synthetic fixture.

## Public benchmark adapters

Adapters exist for:

| Dataset | Official source | Repository inclusion |
| --- | --- | --- |
| HotpotQA | <https://hotpotqa.github.io/> | Not included |
| MuSiQue | <https://github.com/StonyBrookNLP/musique> | Not included |
| 2WikiMultiHopQA | <https://github.com/Alab-NII/2wikimultihop> | Not included |

Users must review each source's current license and usage notes. `scripts/download_data.py` lists
expected paths and records hashes but does not bypass license review or redistribute data.

## τ-Knowledge

The supplied τ-Knowledge archive is treated as private and non-redistributable. The adapter
validates archive structure without extraction. The archive, extracted files, derived private
records, model outputs, and traces are excluded from Git, CI, Docker, and public reports.

## Known limitations

MiniRoute is small, synthetic, English-only, and intentionally separable. It is useful for
software validation and controlled failures, not for population-level conclusions.
