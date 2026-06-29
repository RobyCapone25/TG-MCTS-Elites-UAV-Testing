# Case Studies

This folder contains the UAV missions used by the TG-MCTS-Elites generator.

The generator does not modify the mission itself. It modifies only the obstacle configuration around the mission in order to search for unsafe or challenging scenarios.

---

## Main Mission Files

| File | Role |
|---|---|
| `mission1.yaml` | Mission 1 configuration used by the generator |
| `mission2.yaml` | Mission 2 configuration used by the generator |
| `mission3.yaml` | Mission 3 configuration used by the generator |
| `mission1.plan` | Mission 1 QGroundControl plan |
| `mission2.plan` | Mission 2 QGroundControl plan |
| `mission3.plan` | Mission 3 QGroundControl plan |

---

## Running a Mission

From the repository root:

```bash
python cli.py generate case_studies/mission1.yaml 10
```

The second argument is the simulation budget.

For example:

```bash
python cli.py generate case_studies/mission2.yaml 100
```

runs the generator on `mission2.yaml` with a budget of 100 successful simulations.

---

## Mission Role

Each mission defines a reference UAV trajectory or mission plan.

The search algorithm then generates obstacle configurations that satisfy the official constraints and tries to minimize the distance between the UAV trajectory and the generated obstacles.

---

## Generated Outputs

Generated tests are not stored inside this folder.

They are saved locally under:

```text
generated_tests/
results/
```

These folders are ignored by Git because they can become large.
