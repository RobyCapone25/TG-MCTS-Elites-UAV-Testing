# Output Structure

TG-MCTS-Elites creates native search artifacts and final exported test cases.

## Native search artifacts

Each execution creates:

    results/tg_mcts_elites/<run_id>/
    ├── history.csv
    ├── progress_final.png
    ├── tree_final.png
    ├── run_state.json
    ├── scenario_plots/
    ├── evaluated_tests/
    └── checkpoint/

The checkpoint directory contains the data required for diagnostics and
interrupted-run recovery.

## Exported test cases

Selected scenarios are exported to:

    generated_tests/<timestamp>/
    ├── test_0.yaml
    ├── test_0.ulg
    ├── rank01_*.yaml
    ├── rank01_*.ulg
    ├── manifest.csv
    ├── checkpoint.json
    ├── debug.txt
    └── plots/

The `plots/` directory collects the final visual artifacts, including:

- native trajectory plots;
- official-style trajectory plots;
- progress plots;
- MCTS tree plots.

The official-style trajectory plot contains position and yaw signals over
time together with the top-down UAV trajectory and obstacle footprints.

The export-level `checkpoint.json` is an artifact index. Search recovery uses
the native checkpoint stored under `results/tg_mcts_elites/<run_id>/`.
