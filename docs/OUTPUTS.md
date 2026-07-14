# Output Structure

Each run receives one mission-aware identifier:

```text
mission_<number>_<YYYY-MM-DD_HH-MM-SS-microseconds>
```

For example:

```text
mission_1_2026-07-14_12-30-00-123456
```

## Complete run folder

```text
results/tg_mcts_elites/<run-id>/
├── all_failed_cases/
├── best_ranked_failed_tests/
├── checkpoint/
├── history.csv
├── mcts_tree.png
├── tree_final.png
├── progress_min_distance.png
├── progress_reward.png
├── progress_reward_vs_distance.png
└── run_state.json
```

## Checkpoint and metadata files

Every evaluated execution contributes lightweight metadata to:

```text
checkpoint/results.jsonl   # includes mission_status and failure_evidence
checkpoint/history.jsonl
history.csv
run_state.json
```

Additional files are created when applicable:

```text
checkpoint/confirmations.jsonl
checkpoint/pending_candidate.json
checkpoint/invalid_candidates.csv
checkpoint/system_errors.csv
```

## All retained official failures

An input-compliant execution with `minimum_distance < 1.5 m` is stored under, whether its mission outcome is `completed` or `not_completed`:

```text
all_failed_cases/
└── failure_attempt_<attempt>_node_<node>_<label>/
    ├── test.yaml
    ├── flight.ulg
    ├── trajectory_overview.png
    └── trajectory_xy_time.png
```

A confirmation rerun that reproduces an official failure is saved with `confirmation_of_<base-attempt>` in the folder name.

`trajectory_overview.png` contains:

- `X(t)`;
- `Y(t)`;
- `Z(t)`;
- the planar `X-Y` trajectory and rotated obstacles.

`trajectory_xy_time.png` contains the three-dimensional `(X,Y,t)` trajectory.

Safe runs, near misses, and non-completions outside the official distance threshold retain metadata only. Their temporary Aerialist YAML and ULG files are removed.

## Best ranked failed tests

After final selection, the diverse ranked subset is copied to:

```text
best_ranked_failed_tests/
├── ranking.csv
└── rank_<rank>_.../
    ├── test.yaml
    ├── flight.ulg
    ├── trajectory_overview.png
    ├── trajectory_xy_time.png
    └── metadata.json
```

This is the analysis-oriented copy of the final selected suite.

## Search-tree plot

The files

```text
mcts_tree.png
tree_final.png
```

contain the same final tree; `tree_final.png` is retained as a compatibility alias.

Each evaluated node is labeled outside the marker with:

```text
node identifier
minimum distance
reward
```

Marker categories distinguish critical proximity, official failure, near miss, safe, and unevaluated/internal nodes.

## Progress plots

The progress diagnostics are separate images:

```text
progress_min_distance.png
progress_reward.png
progress_reward_vs_distance.png
```

They show respectively:

- minimum distance and best distance so far versus simulator attempt;
- reward and best reward so far versus simulator attempt;
- reward versus minimum distance, annotated by attempt number.

## Challenge-compatible ranking

The CLI exports the same selected tests to:

```text
generated_tests/<same-run-id>/
├── ranking.csv
├── test_0.yaml
├── test_0.ulg
├── test_0_overview.png
├── test_0_xy_time.png
└── ...
```

The folder may contain only `ranking.csv` when no compliant, artifact-backed, sufficiently reproducible, diverse official distance failure is returnable. Both completed and non-completed proximity failures can be selected; `failure_evidence` records the distinction.
