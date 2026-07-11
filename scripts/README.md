# Scripts

This folder contains reproducible helper scripts for setup verification and experiment execution.

---

## Files

| File | Purpose |
|---|---|
| `check_setup.sh` | Verifies Linux, Python, Conda, Docker, Aerialist, `.env`, mission files, and syntax |
| `run_all_100.sh` | Runs 100 simulations for each of the three competition missions |

---

## Verify the Environment

From the repository root:

```bash
conda activate uav
./scripts/check_setup.sh
```

A complete setup prints:

```text
SETUP CHECK PASSED
```

The checker does not start PX4 or consume the search budget.

---

## Full Fresh Experiment

```bash
./scripts/run_all_100.sh
```

This runs:

```text
mission1: 100 successful simulations
mission2: 100 successful simulations
mission3: 100 successful simulations
```

Total:

```text
300 successful simulations
```

The script uses:

```text
TG_FORCE_NEW=1
```

Therefore, it starts a fresh run for each mission.

---

## Resume an Interrupted Mission

Do not use `run_all_100.sh` to resume an interrupted mission.

Resume the relevant mission manually without `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The budget remains the total target, not an additional amount.
