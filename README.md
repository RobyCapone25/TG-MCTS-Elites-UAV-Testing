# TG-MCTS-Elites UAV Test Generator

[![Python checks](https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing/actions/workflows/python-checks.yml/badge.svg)](https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing/actions/workflows/python-checks.yml)

A rule-compliant search-based test generator for the UAV Testing Competition.

The project generates obstacle configurations for PX4-Avoidance missions and searches for scenarios in which the UAV collides with, or passes dangerously close to, obstacles. It combines trajectory-guided generation, Monte Carlo Tree Search, MAP-Elites, rule validation, checkpointing, and crash recovery.

## Highlights

- trajectory-guided obstacle initialization;
- Monte Carlo Tree Search with progressive widening;
- MAP-Elites diversity preservation;
- rotated-obstacle validation and overlap checks;
- physical-feasibility checks;
- mission-completion analysis;
- automatic retry of system-level simulation failures;
- resumable executions with per-candidate checkpointing;
- native and official-style trajectory plots;
- reproducible scripts for all three competition missions.

## System requirements

The project was developed for:

| Component | Requirement |
|---|---|
| Operating system | Linux, tested on Ubuntu |
| Python | 3.10 |
| Environment manager | Conda |
| Docker | Required |
| Aerialist image | `skhatiri/aerialist:2.0` |
| Simulation | PX4 and Gazebo through the Aerialist container |

PX4, Gazebo, and ROS do not need to be installed manually on the host for the standard Docker workflow.

## Installation

```bash
git clone https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing.git
cd TG-MCTS-Elites-UAV-Testing

conda env create -f environment.yml
conda activate uav

cp .env.example .env
docker pull skhatiri/aerialist:2.0
```

Detailed setup instructions are available in [`docs/SETUP.md`](docs/SETUP.md).

## Quick start

Run one fresh simulation for Mission 1:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 1
```

The root `cli.py` is a launcher. The actual command-line implementation is in `src/cli.py`.

## Full experiment

Run 100 simulations for each competition mission:

```bash
./scripts/run_all_harmonized_100.sh
```

Run one mission with harmonized outputs:

```bash
./scripts/run_harmonized.sh case_studies/mission1.yaml 100 --fresh
```

The legacy experiment launcher remains available as:

```bash
./scripts/run_all_100.sh
```

## Resume an interrupted run

Do not set `TG_FORCE_NEW=1` when resuming:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The budget is interpreted as the total target. For example, if 37 successful simulations were completed before an interruption, the resumed execution continues from simulation 38 and stops at 100.

## Objective and result classes

The optimized quantity is the minimum UAV-obstacle distance:

```text
min_distance = minimum distance between the UAV trajectory and all generated obstacles
```

| Result class | Condition |
|---|---|
| Hard fail | `min_distance < 0.25 m` |
| Soft fail | `0.25 m <= min_distance < 1.5 m` |
| Near miss | `1.5 m <= min_distance < 3.0 m` |
| Safe | `min_distance >= 3.0 m` |

The search favors official failures, smaller minimum distances, completed missions, fewer obstacles, and shorter simulations.

## TG-MCTS-Elites

TG-MCTS-Elites combines:

1. **Trajectory-Guided generation** to sample obstacles near expected mission corridors.
2. **Monte Carlo Tree Search** to select and expand promising obstacle configurations.
3. **MAP-Elites** to retain high-quality scenarios across different behavioral cells.

The MCTS selection score follows:

```text
UCB = mean_reward + C * sqrt(log(parent_visits + 1) / child_visits)
```

The archive descriptor includes obstacle count, position bins, compactness, and rotation.

A complete technical description is available in [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

## Rule compliance

Each obstacle is a rotated box with:

```text
position = (x, y, z, r)
size     = (l, w, h)
```

The implementation enforces:

| Parameter | Constraint |
|---|---|
| `x` | `-40 <= x <= 30` |
| `y` | `10 <= y <= 40` |
| `z` | `z = 0` |
| `l` | `2 <= l <= 20` |
| `w` | `2 <= w <= 20` |
| `h` | `10 < h <= 25` |
| `r` | `0 <= r <= 90` |
| Obstacles | at most `3` |
| Overlap | forbidden |
| Feasibility | the layout must preserve a physically feasible corridor |

## Outputs

Native search artifacts are written to:

```text
results/tg_mcts_elites/<run_id>/
├── history.csv
├── progress_final.png
├── tree_final.png
├── run_state.json
├── evaluated_tests/
├── scenario_plots/
└── checkpoint/
```

Selected test cases are exported to:

```text
generated_tests/<timestamp>/
├── test_0.yaml
├── test_0.ulg
├── rank01_*.yaml
├── rank01_*.ulg
├── manifest.csv
├── checkpoint.json
├── debug.txt
└── plots/
    ├── test_0_native.png
    ├── test_0_official.png
    ├── rank01_*_plot.png
    ├── progress_final.png
    └── tree_final.png
```

The official-style plot includes X, Y, altitude, and yaw over time, together with a top-down trajectory view and rotated obstacle footprints.

See [`docs/OUTPUTS.md`](docs/OUTPUTS.md) for details.

## Repository structure

```text
.
├── .github/workflows/
├── case_studies/
├── docs/
│   ├── ALGORITHM.md
│   ├── OUTPUTS.md
│   ├── SETUP.md
│   └── uml/
├── scripts/
│   ├── run_all_100.sh
│   ├── run_all_harmonized_100.sh
│   └── run_harmonized.sh
├── src/
│   ├── cli.py
│   ├── plot_official.py
│   ├── random_generator.py
│   └── testcase.py
├── CITATION.cff
├── Dockerfile
├── README.md
├── cli.py
├── environment.yml
└── requirements.txt
```

## Main source files

- `src/random_generator.py`: TG-MCTS-Elites search, rule validation, checkpointing, ranking, and native plots.
- `src/testcase.py`: Aerialist/PX4 test execution and distance extraction.
- `src/cli.py`: command-line workflow and final artifact export.
- `src/plot_official.py`: official-style ULog trajectory visualization.
- `cli.py`: root launcher.

## UML documentation

Mermaid sources are stored in:

- `docs/uml/class_diagram.mmd`
- `docs/uml/execution_flow.mmd`
- `docs/uml/sequence_diagram.mmd`

They can be edited with Mermaid Live Editor and reviewed directly on GitHub.

## Citation

Citation metadata is provided in [`CITATION.cff`](CITATION.cff). GitHub will expose a **Cite this repository** action after the file is merged into the default branch.

## Generated and local-only data

The following are intentionally excluded from version control:

```text
generated_tests/
results/
logs/
*.ulg
.env
__pycache__/
backups/
```

## Context

This project was developed for the UAV Testing Competition using PX4-Avoidance and Aerialist, with a focus on automated, search-based generation of obstacle scenarios for UAV simulation.
