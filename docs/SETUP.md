# Setup Guide

This guide explains how to install, configure, verify, run, and resume the
TG-MCTS-Elites UAV test generator.

## Architecture

The recommended architecture is:

```text
Linux / Ubuntu host
    |
    |-- Conda environment: Python 3.10
    |       |
    |       |-- TG-MCTS-Elites source
    |       |-- Aerialist Python package v1.0
    |
    |-- Docker
            |
            |-- skhatiri/aerialist:2.0
                    |
                    |-- PX4
                    |-- PX4-Avoidance
                    |-- ROS
                    |-- Gazebo
```

PX4, PX4-Avoidance, ROS, and Gazebo do not need to be installed manually on the
host for the recommended Docker workflow.

## Supported and pinned components

| Component | Requirement |
|---|---|
| Host operating system | Linux; tested on Ubuntu |
| Host architecture | x86-64 recommended |
| Python | 3.10 |
| Environment manager | Conda |
| Docker | Required for the recommended workflow |
| Host Aerialist package | Git tag `v1.0` |
| Simulation image | `skhatiri/aerialist:2.0` |
| Standard host agent | `docker` |
| Standard simulator | `ros` |
| Standard robot | `px4_ros` |

`requirements.txt` pins the direct Python packages used by this repository to
versions compatible with the Aerialist `v1.0` dependency set.

## 1. Clone the repository

```bash
git clone https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing.git
cd TG-MCTS-Elites-UAV-Testing
```

## 2. Install Docker on Ubuntu

A distribution package can be installed with:

```bash
sudo apt update
sudo apt install docker.io -y
sudo systemctl enable --now docker
```

Verify Docker:

```bash
docker --version
docker run --rm hello-world
```

Allow the current user to run Docker without `sudo`:

```bash
sudo usermod -aG docker "$USER"
```

Log out and log back in after changing group membership.

## 3. Pull the simulation image

```bash
docker pull skhatiri/aerialist:2.0
docker image inspect skhatiri/aerialist:2.0 >/dev/null
```

The explicit `2.0` tag is used instead of `latest`.

## 4. Create the Conda environment

```bash
conda env create -f environment.yml
conda activate uav
```

To update an existing environment:

```bash
conda env update -f environment.yml --prune
conda activate uav
```

The environment installs the Aerialist Python API from tag `v1.0` and the
pinned direct dependencies listed in `requirements.txt`.

## 5. Manual Python installation

For an existing Python 3.10 environment:

```bash
python -m pip install "git+https://github.com/skhatiri/Aerialist.git@v1.0"
python -m pip install -r requirements.txt
```

Verify imports:

```bash
python - <<'PY'
import aerialist
import decouple
import matplotlib
import numpy
import pandas
import yaml
import munch
import pyparsing

print("All required Python imports succeeded.")
PY
```

## 6. Configure `.env`

Create the local runtime file:

```bash
cp .env.example .env
```

The recommended host configuration is:

```env
LOGS_COPY_DIR=results/
RESULTS_DIR=results/
TESTS_FOLDER=generated_tests/

AGENT=docker
SIMULATOR=ros
SPEED=1
ROBOT=px4_ros
HEADLESS=True

USE_GPS=False
PLOT_TESTS_XYZ=False
ALLIGN_ORIGIN=True
USE_RADIANS=False
LOAD_HOME_FROM_LOG=True

DOCKER_IMG=skhatiri/aerialist:2.0
DOCKER_TIMEOUT=1000
```

The real `.env` file is ignored by Git. Only `.env.example` is versioned.

## 7. Verify the setup

Activate the environment and run:

```bash
conda activate uav
./scripts/check_setup.sh
```

The checker validates:

- Linux;
- active Conda environment;
- Python 3.10;
- required Python imports;
- Docker access without `sudo`;
- the required Docker image;
- `.env` values;
- repository files;
- Python syntax;
- shell syntax;
- YAML/CFF syntax when PyYAML is available;
- the unit-test suite.

The final line should be:

```text
SETUP CHECK PASSED
```

## 8. Run a quick smoke experiment

Run one fresh simulator attempt:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 1
```

A successful program execution prints a minimum distance for each evaluated
simulation and eventually reports:

```text
<n> diverse official failure test cases generated
output folder: ...
complete run data: ...
```

`<n>` can legitimately be zero. One simulator attempt does not guarantee an
official failure.

Local outputs are written under:

```text
results/
generated_tests/
logs/
```

## 9. Run a larger experiment

Example with a strict total budget of 100 simulator attempts:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 100
```

The budget includes successful evaluations, system-error attempts, retries, and
confirmation reruns.

## 10. Run all supplied missions

```bash
./scripts/run_all_100.sh
```

The script starts one fresh 100-attempt run for each mission:

```text
mission1: at most 100 simulator attempts
mission2: at most 100 simulator attempts
mission3: at most 100 simulator attempts
```

The aggregate declared budget is 300 simulator attempts. The number of
successful evaluations can be smaller because infrastructure errors and
post-execution rejections consume budget.

## 11. Crash recovery

Recovery data are stored under:

```text
results/tg_mcts_elites/<run-id>/
```

Important files include:

```text
run_state.json
checkpoint/pending_candidate.json
checkpoint/results.jsonl
checkpoint/history.jsonl
checkpoint/confirmations.jsonl
checkpoint/system_errors.csv
checkpoint/invalid_candidates.csv
```

After a PC, Docker, Gazebo, PX4, or process interruption, resume the same mission
without `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The numeric value is the total target budget. If 37 attempts are already
recorded, the resumed run continues toward 100 rather than adding 100 more.

Do not use a fresh-run script to resume an interrupted mission.

## 12. Fixed search seed

Use:

```bash
TG_SEED=12345 TG_FORCE_NEW=1 \
python cli.py generate case_studies/mission1.yaml 100
```

The seed is stored in `run_state.json`.

`TG_SEED` controls Python random choices in the generator. It does not make PX4,
Gazebo, Docker scheduling, or flight trajectories bit-for-bit deterministic.

## 13. Dockerfile workflow

The project Dockerfile inherits:

```dockerfile
FROM skhatiri/aerialist:2.0
```

Inside that image, `AGENT=local` is used because the simulation environment is
already available in the same container.

This differs from the recommended host workflow:

```text
Host workflow:      AGENT=docker
Project container:  AGENT=local
```

Do not change the host `.env` from `docker` to `local`.

Build the project image with:

```bash
docker build -t tg-mcts-elites-uav .
```

## 14. Aerialist log levels

Aerialist can display part of a container transcript at `ERROR` level even when
the simulation completes. Treat the run as successful when the transcript also
contains completion messages and a minimum-distance result.

Retryable infrastructure failures are reported explicitly by TG-MCTS-Elites as
system errors and recorded in `checkpoint/system_errors.csv`.

## 15. Hosted continuous integration

The GitHub Actions workflow performs checks that do not require the simulator:

- compilation of all tracked Python files;
- shell syntax;
- YAML and CFF parsing;
- required-file checks;
- documentation terminology checks.

PX4/Gazebo execution and the complete dependency-backed unit suite remain local
validation tasks.

## 16. Generated and local-only files

The following are intentionally excluded from Git:

```text
results/
logs/
generated_tests/
*.ulg
*.bag
*.log
.env
local backup directories
```

## 17. Common problems

### `ModuleNotFoundError: No module named 'decouple'`

```bash
conda activate uav
conda env update -f environment.yml --prune
```

### `ModuleNotFoundError: No module named 'aerialist'`

```bash
python -m pip install "git+https://github.com/skhatiri/Aerialist.git@v1.0"
```

### Docker permission denied

```bash
sudo usermod -aG docker "$USER"
```

Then log out and log back in.

### Required Docker image missing

```bash
docker pull skhatiri/aerialist:2.0
```

### `.env` missing

```bash
cp .env.example .env
```

### Resume instead of starting again

Omit `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

### Mission path does not intersect the legal area

Verify that the YAML references the intended QGroundControl `.plan` and that the
plan contains a non-zero geographic path. The generator evaluates eight
axis/sign mappings automatically, but it cannot construct a reference path when
none intersects the legal obstacle domain.
