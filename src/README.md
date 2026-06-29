# Source Code

This folder contains the implementation of the TG-MCTS-Elites UAV test generator.

The root-level `cli.py` file is only a launcher. The actual command-line implementation and algorithmic code are inside this folder.

---

## Files

| File | Role |
|---|---|
| `cli.py` | Command-line implementation |
| `random_generator.py` | Main TG-MCTS-Elites search algorithm |
| `testcase.py` | Aerialist/PX4 test-case wrapper |
| `__init__.py` | Python package marker |

---

## Main Entry Point

From the repository root, run:

```bash
python cli.py generate case_studies/mission1.yaml 10
```

The root `cli.py` forwards execution to:

```text
src/cli.py
```

---

## Main Algorithm

The main algorithm is implemented in:

```text
src/random_generator.py
```

It contains:

- trajectory-guided obstacle generation;
- Monte Carlo Tree Search;
- MAP-Elites archive;
- rule-compliant obstacle validation;
- rotated obstacle geometry;
- simulation execution;
- checkpointing and crash recovery;
- result ranking;
- progress and tree plotting.

---

## Test-Case Wrapper

The file:

```text
src/testcase.py
```

wraps Aerialist/PX4 execution.

It is responsible for:

- creating executable test cases;
- launching simulations;
- handling Aerialist outputs;
- extracting obstacle distances;
- saving generated YAML files and logs.
