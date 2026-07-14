# Source Code

The root `cli.py` is a lightweight launcher that prepends `src/` to
`sys.path` and executes `src/cli.py`.

## Public names

The descriptive public class is:

```python
from tg_mcts_elites import TGMCTSElitesGenerator
```

`src/random_generator.py` is a compatibility layer. Its `RandomGenerator` name
resolves to the same class and is not an independent random baseline.

## Modules

| Path | Responsibility |
|---|---|
| `cli.py` | command-line parsing and challenge-compatible ranking export |
| `testcase.py` | Aerialist/PX4 execution wrapper |
| `random_generator.py` | compatibility exports for `TGMCTSElitesGenerator` and `RandomGenerator` |
| `tg_mcts_elites/generator.py` | search orchestration and phase control |
| `tg_mcts_elites/config.py` | constants, thresholds, and budget policies |
| `tg_mcts_elites/models.py` | `MCTSNode`, `EvalResult`, and persisted test wrappers |
| `tg_mcts_elites/mission.py` | case-study resolution, QGroundControl parsing, and frame inference |
| `tg_mcts_elites/geometry.py` | rotated-box geometry and overlap primitives |
| `tg_mcts_elites/validation.py` | obstacle constraints and corridor feasibility |
| `tg_mcts_elites/scenarios.py` | mission-guided initialization and mutation operators |
| `tg_mcts_elites/archive.py` | MAP-Elites descriptor and elite replacement |
| `tg_mcts_elites/scoring.py` | official points, reward, evidence, confirmation statistics, and ranking |
| `tg_mcts_elites/mcts.py` | UCB, progressive widening, expansion, and backup |
| `tg_mcts_elites/trajectory.py` | trajectory extraction, time series, and mission outcome |
| `tg_mcts_elites/simulation.py` | strict-budget execution and retry handling |
| `tg_mcts_elites/confirmation.py` | budget-aware reruns of leading failures |
| `tg_mcts_elites/persistence.py` | run naming, checkpoints, resume, cleanup, and artifacts |
| `tg_mcts_elites/plotting.py` | scenario, `(X,Y,t)`, tree, progress, and ranking plots |
| `tg_mcts_elites/selection.py` | robust filtering and dual diversity selection |

## Dependency direction

```text
root cli.py
    -> src/cli.py
        -> tg_mcts_elites.TGMCTSElitesGenerator
            -> composed mixins and data models

Legacy external imports:
    random_generator.RandomGenerator
        -> alias of tg_mcts_elites.TGMCTSElitesGenerator
```

## Tests

The `tests/` directory verifies score semantics, non-completed proximity
retention, generator-name compatibility, mission parsing and frame conversion,
output layout, progress plots, diversity, confirmation-aware ranking, and
cross-module method contracts.
