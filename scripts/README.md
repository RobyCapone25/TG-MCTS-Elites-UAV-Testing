# Scripts

| File | Purpose |
|---|---|
| `check_setup.sh` | Verifies the host environment, repository files, syntax, YAML/CFF, Docker configuration, and unit tests |
| `run_mission1_50.sh` | Starts a fresh Mission 1 run with a strict 50-attempt budget and records the terminal transcript |
| `run_all_100.sh` | Starts fresh 100-attempt runs for Missions 1, 2, and 3 and records one transcript per mission |

## Validate the environment

```bash
conda activate uav
./scripts/check_setup.sh
```

## Mission 1 experiment

```bash
./scripts/run_mission1_50.sh
```

The budget includes successful evaluations, system-error attempts, retries, and
confirmation reruns.

## Full experiment

```bash
./scripts/run_all_100.sh
```

The declared aggregate budget is 300 simulator attempts.

## Resume

The supplied scripts force new runs. Resume an interrupted mission manually by
omitting `TG_FORCE_NEW=1`:

```bash
PYTHONPATH="$PWD/src" \
python cli.py generate case_studies/mission1.yaml 50
```

The numeric value remains the total target attempt budget.
