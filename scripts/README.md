# Scripts

This folder contains helper scripts used to run experiments.

---

## Files

| File | Role |
|---|---|
| `run_all_100.sh` | Runs 100 simulations for each of the three missions |

---

## Full Experiment

From the repository root, run:

```bash
./scripts/run_all_100.sh
```

This executes:

```text
mission1: 100 simulations
mission2: 100 simulations
mission3: 100 simulations
```

Total:

```text
100 x 3 = 300 simulations
```

---

## Important Note About Fresh Runs

The script uses:

```text
TG_FORCE_NEW=1
```

This means each mission starts as a fresh run.

---

## Crash Recovery

If a run crashes, do not restart with `TG_FORCE_NEW=1`.

Instead, resume the interrupted mission manually.

Example:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The value `100` means total target budget, not 100 additional simulations.

For example, if 37 simulations were already completed before the crash, the resumed run continues from simulation 38 and stops at 100.
