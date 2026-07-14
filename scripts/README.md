# Scripts

| File | Purpose |
|---|---|
| `check_setup.sh` | Existing environment and policy verification script; unchanged by this update |
| `run_mission1_50.sh` | Starts a fresh Mission 1 experiment with a strict budget of 50 simulator attempts and records the terminal transcript |
| `run_all_100.sh` | Starts fresh 100-attempt runs for Missions 1, 2, and 3 |

## Mission 1 experiment

```bash
./scripts/run_mission1_50.sh
```

The budget includes successful executions, confirmation reruns, and infrastructure retries.

## Full experiment

```bash
./scripts/run_all_100.sh
```

## Resume

Resume a mission manually without `TG_FORCE_NEW=1`:

```bash
PYTHONPATH="$PWD/src" python cli.py generate case_studies/mission1.yaml 50
```

The numeric value remains the total target attempt budget.
