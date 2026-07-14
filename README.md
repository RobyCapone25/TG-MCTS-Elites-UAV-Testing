# TG-MCTS-Elites UAV Testing

[![Python checks](https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing/actions/workflows/python-checks.yml/badge.svg?branch=main)](https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing/actions/workflows/python-checks.yml)
[![Python 3.10](https://img.shields.io/badge/Python-3.10-3776AB.svg)](https://www.python.org/)
[![Research prototype](https://img.shields.io/badge/status-research%20prototype-orange.svg)](#project-status)

Mission-guided, search-based test generation for the
[UAV Testing Competition](https://github.com/skhatiri/UAV-Testing-Competition).
The generator combines Monte Carlo Tree Search, progressive widening,
MAP-Elites, strict simulator-attempt accounting, robustness confirmation, and
diversity-aware final selection to discover challenging PX4-Avoidance obstacle
configurations.

## Project status

This repository is a research and competition prototype. It is intended for
simulation-based testing and experimental evaluation; it is not a flight-safety
certification tool.

The current implementation:

- supports the three supplied competition missions;
- uses Aerialist with PX4, PX4-Avoidance, ROS, and Gazebo;
- records distance-based failure evidence without claiming an unobserved
  collision;
- supports checkpoint/resume after interrupted runs;
- retains heavy artifacts only for official distance failures;
- returns a robustness- and diversity-filtered final suite.

## Authors

| Name | Email | Affiliation |
|---|---|---|
| Roberto Capone | roberto.capone@mail.polimi.it | Politecnico di Milano; CentraleSupélec, Université Paris-Saclay |
| Guglielmo Cattaneo | guglielmo1.cattaneo@mail.polimi.it | Politecnico di Milano |

## Quick start

The recommended environment is Linux with Python 3.10, Conda, Docker, the
Aerialist Python package at tag `v1.0`, and the Docker image
`skhatiri/aerialist:2.0`.

```bash
conda env create -f environment.yml
conda activate uav
cp .env.example .env
docker pull skhatiri/aerialist:2.0
./scripts/check_setup.sh
```

Run a fresh Mission 1 experiment:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 50
```

The command-line interface is:

```text
generate <case-study-yaml> <simulator-attempt-budget>
```

The second argument is a strict upper bound on real simulator executions.
Successful evaluations, system-error attempts, retries, post-execution
rejections, and confirmation reruns each consume one budget unit.
Pre-execution invalid candidates do not consume budget.

For the complete installation procedure, see
[`docs/SETUP.md`](docs/SETUP.md).

## Failure and score semantics

The official distance score implemented by the generator is:

| Minimum UAV-obstacle distance | Official point |
|---:|---:|
| `d < 0.25 m` | 5 |
| `0.25 m <= d < 1.0 m` | 2 |
| `1.0 m <= d < 1.5 m` | 1 |
| `d >= 1.5 m` | 0 |

An **official distance failure** satisfies `d < 1.5 m`.

The label `critical_proximity` identifies the 5-point distance band. It is not
independent proof of collision. Mission completion is stored separately as
`completed`, `not_completed`, or `unknown`. A non-completed mission is eligible
for the final suite only when it also satisfies the official distance threshold
and has complete retained evidence.

The `failure_evidence` field distinguishes observations such as:

- `critical_proximity`;
- `official_proximity`;
- `noncompleted_critical_proximity`;
- `noncompleted_official_proximity`;
- `noncompleted_without_official_proximity`;
- `unknown_completion`;
- `none`.

## Algorithm overview

TG-MCTS-Elites:

1. resolves the QGroundControl `.plan` referenced by the case-study YAML;
2. converts geographic waypoints to a local metric path;
3. infers the simulator axis/sign mapping that best intersects the legal
   obstacle domain;
4. generates mission-guided single-blocker, gate, and staggered scenarios;
5. explores scenario mutations with MCTS, UCB selection, and progressive
   widening;
6. stores behaviorally distinct high-quality candidates in a MAP-Elites archive;
7. executes candidates under one strict global simulator-attempt budget;
8. records mission outcome and distance-based failure evidence separately;
9. reruns leading failures for robustness confirmation when budget permits;
10. ranks failures using mean score, reproducibility, distance, simplicity, and
    runtime;
11. filters the final suite using obstacle-geometry distance and trajectory-DTW
    diversity.

See [`docs/ALGORITHM.md`](docs/ALGORITHM.md) for the mathematical and
implementation-level description.

## Source architecture

```text
src/
├── cli.py
├── testcase.py
├── random_generator.py          # compatibility layer
└── tg_mcts_elites/
    ├── generator.py             # TGMCTSElitesGenerator orchestration
    ├── config.py                # constants and thresholds
    ├── models.py                # search-tree and result data structures
    ├── mission.py               # YAML/.plan parsing and frame inference
    ├── geometry.py              # rotated-box geometry
    ├── validation.py            # competition and feasibility checks
    ├── scenarios.py             # initialization and mutation operators
    ├── archive.py               # MAP-Elites descriptors and archive
    ├── scoring.py               # score, reward, evidence, and ranking
    ├── mcts.py                  # UCB, expansion, and backup
    ├── trajectory.py            # trajectory and mission outcome extraction
    ├── simulation.py            # execution, retries, and budget accounting
    ├── confirmation.py          # robustness confirmation reruns
    ├── persistence.py           # checkpoints and artifact retention
    ├── plotting.py              # scenario, tree, and progress plots
    ├── selection.py             # robust and diverse final selection
    ├── benchmark.py             # append-only benchmark recording and metrics
    └── random_search.py         # operator-matched random-search baseline
```

`TGMCTSElitesGenerator` is the descriptive public class. `RandomGenerator`
remains an alias only for backward compatibility:

```python
from tg_mcts_elites import TGMCTSElitesGenerator

# Compatibility with older competition scripts:
from random_generator import RandomGenerator
```

## Operator-matched random-search benchmark

The repository includes a distinct `RandomSearchGenerator` baseline. It shares
the same mission-derived scenario operators, validation, simulator, strict
budget, scoring, confirmation, persistence, and final diversity filters as
TG-MCTS-Elites. It differs in search control: parent and action choices are
uniform, and it does not use UCB, progressive-widening control, reward backup,
or the MAP-Elites archive to generate candidates.

The historical command remains unchanged:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

Select either algorithm explicitly with:

```bash
python cli.py generate case_studies/mission1.yaml 100 --algorithm tg-mcts-elites
python cli.py generate case_studies/mission1.yaml 100 --algorithm random-search
```

Run one paired comparison:

```bash
./scripts/run_benchmark_pair.sh mission1 100 12345
```

Run the restart-safe two-seed campaign:

```bash
./scripts/run_benchmark_two_seeds.sh mission1 50 1001 1002
```

The benchmark recorder writes per-run events and summaries, while the tools in
`tools/` aggregate completed runs and generate explicit paired comparison
plots. See [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

## Output structure

A run receives a mission-aware identifier such as:

```text
mission_1_2026-07-14_12-30-00-123456
```

Complete experiment data are stored in:

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

The challenge-compatible final ranking is exported to:

```text
generated_tests/<same-run-id>/                       # TG-MCTS-Elites
generated_tests/operator_random_search/<same-run-id>/ # random-search baseline
```

Each retained failure contains its YAML test, ULG flight log, trajectory
overview, and `(X,Y,t)` plot. See [`docs/OUTPUTS.md`](docs/OUTPUTS.md) for the
complete retention policy.

## Reproducibility and recovery

Use a fixed Python search seed:

```bash
TG_SEED=12345 TG_FORCE_NEW=1 \
python cli.py generate case_studies/mission1.yaml 50
```

`TG_SEED` makes the generator's Python random choices reproducible. It does not
guarantee bit-for-bit deterministic PX4, Gazebo, Docker, operating-system, or
timing behavior.

Resume an incomplete run by omitting `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 50
```

The supplied budget remains the total attempt limit; it is not added to the
attempts already consumed.

## Validation

Run the complete local validation from the activated `uav` environment:

```bash
./scripts/check_setup.sh
```

Or run the unit tests directly:

```bash
PYTHONPATH="$PWD/src" MPLBACKEND=Agg \
python -m unittest discover -s tests -v
```

The tests cover score boundaries, mission-outcome handling, public generator
names, the distinct random-search baseline, mission-plan conversion, frame
inference, geometry and trajectory diversity, confirmation-aware ranking,
restart-safe benchmark recording, aggregation, comparison plotting, output
generation, and cross-module method contracts.

The GitHub Actions workflow performs dependency-free syntax, shell, YAML, and
documentation-consistency checks. Simulator execution is intentionally excluded
from hosted CI.

## Documentation

- [`docs/ALGORITHM.md`](docs/ALGORITHM.md): search, reward, archive,
  confirmation, ranking, and diversity;
- [`docs/OUTPUTS.md`](docs/OUTPUTS.md): run naming, retained artifacts,
  checkpoints, plots, and ranking exports;
- [`docs/SETUP.md`](docs/SETUP.md): installation, configuration, validation,
  execution, and recovery;
- [`docs/uml/`](docs/uml/): Mermaid class, execution-flow, and sequence
  diagrams;
- [`case_studies/`](case_studies/): supplied missions and case-study
  configurations;
- [`docs/BENCHMARK.md`](docs/BENCHMARK.md): operator-matched random-search
  baseline, paired campaigns, restart behavior, metrics, aggregation, and plots;
- [`benchmark/`](benchmark/): benchmark navigation and repository policy.

## Limitations

- The simulator does not currently expose an independent collision flag to this
  generator; collision is therefore never inferred from distance alone.
- Search reproducibility does not imply deterministic simulator trajectories.
- The benchmark framework is implemented, but no statistically conclusive
  performance claim is made until repeated completed runs are available.
- Hosted CI validates repository consistency but does not launch PX4/Gazebo.
- The software has been developed for the supplied competition environment and
  has not been validated for real UAV deployment.

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). GitHub can
render these metadata through the repository's **Cite this repository** action.

## License

No software license has yet been declared. Until the authors add a `LICENSE`
file, standard copyright applies and the public repository does not grant
general reuse, modification, or redistribution rights.

## Acknowledgements

This project builds on
[Aerialist](https://github.com/skhatiri/Aerialist) and the
[UAV Testing Competition](https://github.com/skhatiri/UAV-Testing-Competition)
infrastructure.
