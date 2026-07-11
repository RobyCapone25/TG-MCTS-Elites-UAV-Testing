# TG-MCTS-Elites Algorithm

TG-MCTS-Elites combines three search components:

1. trajectory-guided obstacle generation;
2. Monte Carlo Tree Search;
3. MAP-Elites diversity preservation.

## Search representation

Each MCTS node represents a valid obstacle configuration. An edge represents
an initialization or mutation action applied to that configuration.

## Tree selection

The tree policy uses an Upper Confidence Bound criterion combining:

- exploitation through the mean reward;
- exploration through the visit-count term.

Progressive widening controls how many children may be generated from each
node in the continuous obstacle-parameter space.

## Search actions

The implementation includes actions such as:

- single-obstacle initialization;
- gate initialization;
- staggered initialization;
- local and strong mutation;
- obstacle translation;
- resizing;
- rotation;
- gate tightening;
- adding an obstacle.

## MAP-Elites archive

Candidates are assigned to behavioral cells according to scenario descriptors,
including obstacle count, position, compactness, and rotation.

The highest-quality candidate encountered in each cell is retained.

## Reward

The reward favors:

- official failures;
- small UAV-obstacle distance;
- completed missions;
- simple scenarios with fewer obstacles;
- shorter simulation time.

The authoritative implementation is located in:

```text
src/random_generator.py

Create `docs/OUTPUTS.md`:

```bash
cat > docs/OUTPUTS.md <<'EOF'
# Output Structure

TG-MCTS-Elites creates native search artifacts and final exported test cases.

## Native search artifacts

Each execution creates:

```text
results/tg_mcts_elites/<run_id>/
├── history.csv
├── progress_final.png
├── tree_final.png
├── run_state.json
├── scenario_plots/
├── evaluated_tests/
└── checkpoint/

Create `CITATION.cff`:

```bash
cat > CITATION.cff <<'EOF'
cff-version: 1.2.0
message: "If you use this software, please cite it using the metadata below."
title: "TG-MCTS-Elites UAV Test Generator"
type: software
authors:
  - family-names: "Capone"
    given-names: "Roberto"
repository-code: "https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing"
version: "0.1.0"
date-released: "2026-07-11"
keywords:
  - UAV testing
  - search-based software testing
  - Monte Carlo Tree Search
  - MAP-Elites
  - PX4
  - Aerialist
