# TG-MCTS-Elites versus Operator-Matched Random Search

The repository exposes two generators through the same CLI and simulator budget:

```bash
python cli.py generate case_studies/mission1.yaml 100 --algorithm tg-mcts-elites
python cli.py generate case_studies/mission1.yaml 100 --algorithm random-search
```

The default remains `tg-mcts-elites`, so the historical command is unchanged.

The random baseline uses the same mission-derived initial scenarios, mutation
operators, validation, simulator, retries, official scoring, confirmation
reserve, persistence, MAP-Elites measurement, and final geometry/trajectory
diversity filters. It selects evaluated parents and actions uniformly and does
not use UCB, progressive-widening search control, reward backup, or the archive
to generate candidates.

## Paired run

```bash
./scripts/run_benchmark_pair.sh mission1 100 12345
```

Both algorithms receive the same mission, seed, and strict total simulator
budget. Attempts reserved for confirmation remain inside that total budget.

## Per-run outputs

```text
results/tg_mcts_elites/<run>/benchmark/events.jsonl
results/tg_mcts_elites/<run>/benchmark/summary.json
results/tg_mcts_elites/<run>/benchmark/summary.csv

results/random_search/<run>/benchmark/events.jsonl
results/random_search/<run>/benchmark/summary.json
results/random_search/<run>/benchmark/summary.csv
```

The recorder separates search and confirmation attempts and includes failure
yield, robust official score, time to first failure, archive coverage,
reproducibility, obstacle simplicity, geometry diversity, trajectory-DTW
diversity, proposal rejection counts, simulator errors, and measured time.

## Aggregate repeated seeds

```bash
python tools/aggregate_benchmarks.py
```

The aggregate files are written below `results/benchmark_comparison/`.

## Visual comparison with two paired seeds

The aggregator now creates paired comparison plots automatically:

```bash
python tools/aggregate_benchmarks.py
```

The plots are written below:

```text
results/benchmark_comparison/plots/
```

With only two seeds, each figure shows both paired observations explicitly as
lines from operator-matched random search to TG-MCTS-Elites. The figures do not
use boxplots, confidence intervals, p-values, or significance claims. They cover:

- returnable failure yield;
- diverse failures returned;
- best minimum distance;
- attempt to first official failure;
- archive coverage;
- failure reproducibility.

The plotting step also writes `plot_manifest.csv` and `paired_differences.csv`.
A missing first failure is displayed as `>B` and plotted at `B + 1` only to make
the right-censored observation visible.

To regenerate only the plots:

```bash
python tools/plot_benchmarks.py
```

## Restart-safe two-seed campaign

Run the complete paired experiment for exactly two seeds with:

```bash
./scripts/run_benchmark_two_seeds.sh mission1 50 1001 1002
```

The same command is safe to execute again after a host shutdown, Docker failure,
terminal closure, or manual interruption:

- an exact completed algorithm/mission/seed/budget run is skipped;
- an exact incomplete run is resumed from its checkpoint;
- a pending simulator candidate is retried when budget remains;
- a different seed or budget is never resumed accidentally;
- aggregation uses only finalized completed summaries;
- duplicate completed runs are reduced to the newest exact run;
- CSV, JSON, run-state, tree-state, and benchmark-summary writes are atomic.

The tree checkpoint is stored at:

```text
results/<algorithm>/<run>/checkpoint/tree_state.json
```

It preserves node topology, obstacle scenarios, visits, accumulated reward, best
reward, and evaluation linkage. Therefore, after restart, TG-MCTS-Elites retains
its search statistics and the final tree plot contains both pre-interruption and
post-restart nodes. Progress plots are regenerated from the complete persisted
history.

A hard interruption may consume one simulator budget unit after the strict
attempt counter is saved but before a benchmark event can be appended. Such
attempts are retained in the total budget and reported explicitly as:

```text
unrecorded_or_interrupted_attempts
```

They are never silently removed from the denominator of yield metrics.
