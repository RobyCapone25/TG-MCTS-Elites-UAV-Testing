# TG-MCTS-Elites UAV Testing

Rule-compliant search-based test generation for the UAV Testing Competition. The project combines mission-guided obstacle generation, Monte Carlo Tree Search, MAP-Elites, strict simulator-attempt accounting, confirmation reruns, explicit execution-outcome classification, and diversity-aware final selection.

## Authors

| Name | Email | Affiliation |
|---|---|---|
| Roberto Capone | roberto.capone@mail.polimi.it | Politecnico di Milano; CentraleSupélec, Université Paris-Saclay |
| Guglielmo Cattaneo | guglielmo1.cattaneo@mail.polimi.it | Politecnico di Milano |

## Competition command

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The interface is:

```text
generate <case-study-yaml> <simulator-attempt-budget>
```

The second argument is a strict upper bound on real simulator executions. Successful runs, retries, system-error attempts, rejected post-execution tests, and confirmation reruns all consume one budget unit.

## Failure and score semantics

| Minimum UAV-obstacle distance | Official point |
|---:|---:|
| `d < 0.25 m` | 5 |
| `0.25 <= d < 1.0 m` | 2 |
| `1.0 <= d < 1.5 m` | 1 |
| `d >= 1.5 m` | 0 |

A test is an official distance failure when `d < 1.5 m`. The implementation labels `d < 0.25 m` as `critical_proximity`; it does not claim a collision without an independent collision signal. A non-completed mission is retained when it also satisfies the official distance threshold and is reported with explicit `failure_evidence`, such as `noncompleted_critical_proximity`.

## Algorithm overview

TG-MCTS-Elites performs the following steps:

1. parse the QGroundControl `.plan` referenced by the case-study YAML;
2. infer the simulator-frame mapping that makes the mission intersect the legal obstacle domain;
3. generate mission-guided single-obstacle, gate, and staggered scenarios;
4. explore mutations with MCTS, UCB selection, and progressive widening;
5. preserve quality and behavioral coverage with MAP-Elites;
6. execute each candidate under a strict global simulator-attempt budget;
7. retain heavy artifacts for compliant official distance failures, including non-completed proximity failures;
8. keep non-completion as an execution outcome rather than an input-compliance error;
9. rerun leading failures for robustness confirmation when the budget permits;
10. rank failures using observed score, reproducibility, distance, simplicity, and runtime;
11. filter the final suite by obstacle-geometry distance and trajectory-DTW diversity.

See [`docs/ALGORITHM.md`](docs/ALGORITHM.md) for the complete technical description.

## Source architecture

```text
src/
├── cli.py
├── testcase.py
├── random_generator.py          # compatibility alias for the old class name
└── tg_mcts_elites/
    ├── generator.py             # TGMCTSElitesGenerator orchestration
    ├── config.py                # constants and thresholds
    ├── models.py                # search-tree and result data structures
    ├── mission.py               # YAML/.plan parsing and frame inference
    ├── geometry.py              # rotated-box geometry
    ├── validation.py            # competition and feasibility checks
    ├── scenarios.py             # initialization and mutation operators
    ├── archive.py               # MAP-Elites descriptors and archive
    ├── scoring.py               # official points, reward, robust ranking
    ├── mcts.py                  # selection, expansion, and backup
    ├── trajectory.py            # trajectory and mission-completion extraction
    ├── simulation.py            # execution, retries, and budget accounting
    ├── confirmation.py          # failure confirmation reruns
    ├── persistence.py           # checkpoints and artifact retention
    ├── plotting.py              # trajectory, tree, and progress plots
    └── selection.py             # diverse final-suite selection
```

`TGMCTSElitesGenerator` is the descriptive public class name. The old `RandomGenerator` name remains an alias so existing scripts continue to work:

```python
from tg_mcts_elites import TGMCTSElitesGenerator

# Backward compatibility only:
from random_generator import RandomGenerator
```

## Output structure

A Mission 1 run receives a meaningful identifier such as:

```text
mission_1_2026-07-14_12-30-00-123456
```

The complete experiment folder is:

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

Each retained failure contains:

```text
test.yaml
flight.ulg
trajectory_overview.png
trajectory_xy_time.png
```

`trajectory_overview.png` contains `X(t)`, `Y(t)`, `Z(t)`, and the planar `X-Y` view. `trajectory_xy_time.png` contains the three-dimensional `(X,Y,t)` trajectory.

The challenge-compatible ranking is exported under the same run identifier:

```text
generated_tests/<same-run-id>/
├── ranking.csv
├── test_0.yaml
├── test_0.ulg
├── test_0_overview.png
└── test_0_xy_time.png
```

See [`docs/OUTPUTS.md`](docs/OUTPUTS.md) for the complete retention policy.

## Reproducibility and recovery

Fresh deterministic run:

```bash
TG_SEED=12345 TG_FORCE_NEW=1 \
python cli.py generate case_studies/mission1.yaml 50
```

Resume an incomplete run by omitting `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 50
```

The supplied value remains the total attempt limit, not an additional budget.

## Tests

```bash
PYTHONPATH="$PWD/src" python -m unittest discover -s tests -v
```

The tests cover official score boundaries, non-completed proximity failures, generator-name compatibility, mission-plan conversion, frame inference, geometric and trajectory diversity, confirmation-aware ranking, output generation, and critical method contracts.

## Scripts

```bash
./scripts/run_mission1_50.sh
./scripts/run_all_100.sh
```

## Documentation

- `docs/ALGORITHM.md`: algorithm, reward, archive, confirmation, and final selection;
- `docs/OUTPUTS.md`: run naming, retained artifacts, ranking folders, and plots;
- `docs/uml/`: Mermaid class, flow, and sequence diagrams;
- `docs/SETUP.md`: existing setup and system-requirement documentation, intentionally unchanged by this update;
- `benchmark/`: empty versioned placeholder reserved for the future benchmark implementation.
