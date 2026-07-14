# Output Structure

Each run receives one mission-aware identifier:

```text
mission_<number>_<YYYY-MM-DD_HH-MM-SS-microseconds>
```

Example:

```text
mission_1_2026-07-14_12-30-00-123456
```

The same identifier is used for the complete analysis folder and the
challenge-compatible ranking folder.

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

## Run state

`run_state.json` records the current status and recovery information, including:

- case-study path and basename;
- mission label;
- total requested budget;
- consumed simulator attempts;
- successful evaluations;
- official failures;
- confirmation observations;
- Python search seed;
- mission-plan path and source;
- diversity thresholds;
- update timestamp.

The file is rewritten and synchronized during execution so that interrupted
runs can be resumed.

## Checkpoint files

Every evaluated search execution contributes lightweight metadata to:

```text
checkpoint/results.jsonl
checkpoint/history.jsonl
history.csv
```

Additional files are created when applicable:

```text
checkpoint/confirmations.jsonl
checkpoint/pending_candidate.json
checkpoint/invalid_candidates.csv
checkpoint/system_errors.csv
```

`results.jsonl` includes obstacle parameters, score, reward, mission outcome,
`failure_evidence`, artifact paths, trajectory samples, and confirmation
statistics available at the time of persistence.

`pending_candidate.json` identifies the candidate that should be recomputed
after an interruption when budget remains.

## All retained official failures

Every input-compliant execution satisfying `minimum_distance < 1.5 m` is stored,
whether its mission outcome is `completed` or `not_completed`:

```text
all_failed_cases/
└── failure_attempt_<attempt>_node_<node>_<label>/
    ├── test.yaml
    ├── flight.ulg
    ├── trajectory_overview.png
    └── trajectory_xy_time.png
```

A confirmation rerun that reproduces an official distance failure includes

```text
confirmation_of_<base-attempt>
```

in its folder name.

Safe executions, near misses, and non-completions outside the official distance
threshold retain metadata only. Their temporary Aerialist YAML and ULG files are
removed.

## Failure plots

`trajectory_overview.png` contains:

- \(X(t)\);
- \(Y(t)\);
- \(Z(t)\);
- the planar \(X-Y\) trajectory;
- rotated obstacle footprints;
- attempt, node, score band, minimum distance, mission outcome, and evidence
  metadata.

`trajectory_xy_time.png` contains the three-dimensional \((X,Y,t)\) trajectory
and obstacle footprints at the initial time plane.

## Best ranked failed tests

After robust ranking and diversity filtering, the selected suite is copied to:

```text
best_ranked_failed_tests/
├── ranking.csv
└── rank_<rank>_point_<point>_distance_<distance>_attempt_<attempt>/
    ├── test.yaml
    ├── flight.ulg
    ├── trajectory_overview.png
    ├── trajectory_xy_time.png
    └── metadata.json
```

This folder is the analysis-oriented copy of the final suite. Its ranking file
contains score, reward, mission outcome, and `failure_evidence`.

## Search-tree plots

The files

```text
mcts_tree.png
tree_final.png
```

contain the same final tree. `tree_final.png` is retained as a compatibility
alias.

Each evaluated node is annotated with:

```text
node identifier
minimum distance
reward
```

Markers distinguish:

- critical proximity;
- official distance failure;
- near miss;
- safe evaluation;
- unevaluated or internal node.

Tree structure is computed from the search itself regardless of whether safe
scenario artifacts are retained.

## Progress plots

Three separate diagnostics are produced:

```text
progress_min_distance.png
progress_reward.png
progress_reward_vs_distance.png
```

They show:

1. minimum distance per evaluated attempt and best distance so far;
2. reward per evaluated attempt and best reward so far;
3. reward versus minimum distance, annotated by attempt number.

Confirmation executions are included in progress history even though they are
not MCTS child nodes.

## Challenge-compatible ranking

The CLI exports the final selected suite to:

```text
generated_tests/<same-run-id>/
├── ranking.csv
├── test_0.yaml
├── test_0.ulg
├── test_0_overview.png
├── test_0_xy_time.png
└── ...
```

`ranking.csv` includes:

- initial minimum distance and point;
- mean point;
- failure reproducibility;
- number of observations;
- mean minimum distance;
- reward;
- problem type;
- mission outcome;
- `failure_evidence`;
- exported artifact filenames.

The folder can contain only `ranking.csv` when no compliant, artifact-backed,
sufficiently reproducible, diverse official distance failure is returnable.

## Generated data and version control

The following paths are intentionally ignored by Git:

```text
results/
generated_tests/
logs/
*.ulg
*.bag
*.log
```

Published benchmark results should be reduced to documented aggregate data
rather than committing complete simulator output trees.
