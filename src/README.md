# Source Code

The root `cli.py` forwards the competition command to `src/cli.py`. The public import remains compatible through `src/random_generator.py`.

| Path | Responsibility |
|---|---|
| `cli.py` | command-line parsing and final ranking export |
| `testcase.py` | Aerialist/PX4 execution wrapper |
| `random_generator.py` | backward-compatible import of `RandomGenerator` |
| `tg_mcts_elites/generator.py` | search orchestration and phase control |
| `tg_mcts_elites/config.py` | constants, thresholds, and budget policies |
| `tg_mcts_elites/models.py` | `MCTSNode`, `EvalResult`, and persisted test wrappers |
| `tg_mcts_elites/mission.py` | case-study mission resolution, QGroundControl parsing, and frame inference |
| `tg_mcts_elites/geometry.py` | rotated-box geometry and overlap primitives |
| `tg_mcts_elites/validation.py` | obstacle constraints and corridor feasibility |
| `tg_mcts_elites/scenarios.py` | mission-guided initialization and mutation operators |
| `tg_mcts_elites/archive.py` | MAP-Elites descriptor and elite replacement |
| `tg_mcts_elites/scoring.py` | official points, reward, confirmation statistics, and ranking |
| `tg_mcts_elites/mcts.py` | UCB, progressive widening, expansion, and backup |
| `tg_mcts_elites/trajectory.py` | trajectory extraction, time series, and mission completion |
| `tg_mcts_elites/simulation.py` | strict-budget execution and retry handling |
| `tg_mcts_elites/confirmation.py` | budget-aware reruns of leading failures |
| `tg_mcts_elites/persistence.py` | run naming, checkpoints, resume, cleanup, and failure artifacts |
| `tg_mcts_elites/plotting.py` | overview, `(X,Y,t)`, tree, progress, and ranking plots |
| `tg_mcts_elites/selection.py` | robust filtering and dual diversity selection |

## Main dependency direction

The mixins contain focused operations and are composed by `RandomGenerator`. The CLI depends on the compatibility import, while the package itself remains independent of the root launcher.

```text
root cli.py
    -> src/cli.py
        -> random_generator.RandomGenerator
            -> tg_mcts_elites.generator.RandomGenerator
```

## Tests

The `tests/` directory verifies core scoring and selection rules, mission parsing and frame conversion, output layout, progress plots, and cross-module method contracts.
