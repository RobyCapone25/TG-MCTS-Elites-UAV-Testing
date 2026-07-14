# Benchmark

The implemented benchmark compares `TGMCTSElitesGenerator` with the distinct
operator-matched `RandomSearchGenerator` under the same mission, seed, strict
simulator-attempt budget, scenario operators, validation, simulator, scoring,
confirmation, persistence, and final selection rules.

The complete protocol is documented in
[`../docs/BENCHMARK.md`](../docs/BENCHMARK.md).

## Main commands

```bash
./scripts/run_benchmark_pair.sh mission1 100 12345
./scripts/run_benchmark_two_seeds.sh mission1 50 1001 1002
python tools/aggregate_benchmarks.py
python tools/plot_benchmarks.py
```

Generated benchmark data are written under `results/` and remain untracked.
The repository does not commit raw simulator logs or claim statistical
significance from the two-seed visualization campaign.

`RandomGenerator` remains a compatibility alias of
`TGMCTSElitesGenerator`; the independent baseline class is
`RandomSearchGenerator`.
