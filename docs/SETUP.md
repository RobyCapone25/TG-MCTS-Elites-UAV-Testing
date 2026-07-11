# Setup Guide

This guide explains how to install, configure, verify, run, and resume the TG-MCTS-Elites UAV test generator.

The recommended architecture is:

```text
Linux / Ubuntu host
    |
    |-- Conda environment: Python 3.10
    |       |
    |       |-- TG-MCTS-Elites source code
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

PX4, PX4-Avoidance, ROS, and Gazebo do not need to be installed manually on the host for the recommended Docker workflow.

---

## Supported and Pinned Components

| Component | Requirement |
|---|---|
| Host operating system | Linux, tested on Ubuntu |
| Host architecture | x86-64 recommended |
| Python | 3.10 |
| Environment manager | Conda |
| Docker | Required |
| Host Aerialist Python package | Git tag `v1.0` |
| Simulation image | `skhatiri/aerialist:2.0` |
| PX4 / Gazebo / ROS | Supplied by the simulation image |
| Standard simulation agent | `docker` |
| Standard simulator setting | `ros` |
| Standard robot setting | `px4_ros` |

The Aerialist Python package installed in Conda provides the Python API imported by the generator.

The Aerialist Docker image provides the PX4/Gazebo/ROS simulation stack.

These are two distinct parts of the setup, and both are required by the standard host-based workflow.

---

## 1. Clone the Repository

```bash
git clone https://github.com/RobyCapone25/TG-MCTS-Elites-UAV-Testing.git
cd TG-MCTS-Elites-UAV-Testing
```

---

## 2. Install Docker on Ubuntu

```bash
sudo apt update
sudo apt install docker.io -y
sudo systemctl enable docker
sudo systemctl start docker
```

Check Docker:

```bash
docker --version
```

Allow the current user to execute Docker without `sudo`:

```bash
sudo usermod -aG docker "$USER"
```

Log out and log back in after running that command.

Verify access:

```bash
docker run --rm hello-world
```

The generator must be able to execute Docker commands without `sudo`.

---

## 3. Pull the Simulation Image

```bash
docker pull skhatiri/aerialist:2.0
```

Verify that it exists locally:

```bash
docker image inspect skhatiri/aerialist:2.0 >/dev/null
```

The project deliberately uses the explicit `2.0` image tag instead of `latest`.

---

## 4. Create the Conda Environment

Create the environment from the repository file:

```bash
conda env create -f environment.yml
```

Activate it:

```bash
conda activate uav
```

The environment installs:

- Python 3.10;
- Aerialist Python package from tag `v1.0`;
- python-decouple;
- matplotlib;
- NumPy;
- pandas;
- PyYAML;
- munch;
- pyparsing.

When the environment already exists, update it with:

```bash
conda env update -f environment.yml --prune
conda activate uav
```

---

## 5. Manual Python Installation Alternative

The Conda file is the recommended method.

For an existing Python 3.10 environment, install Aerialist and the additional dependencies manually:

```bash
python -m pip install "git+https://github.com/skhatiri/Aerialist.git@v1.0"
python -m pip install -r requirements.txt
```

Verify the imports:

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

---

## 6. Configure `.env`

Create the local runtime file:

```bash
cp .env.example .env
```

The recommended configuration is:

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

The real `.env` file is intentionally ignored by Git.

The public `.env.example` file is committed so that new users can reproduce the configuration.

---

## 7. Verify the Complete Setup

Activate the environment:

```bash
conda activate uav
```

Run the automated setup checker:

```bash
./scripts/check_setup.sh
```

It checks:

- Linux;
- active Conda environment;
- Python 3.10;
- required Python imports;
- Docker access without `sudo`;
- the `skhatiri/aerialist:2.0` image;
- `.env`;
- mission files;
- Python syntax;
- shell-script syntax.

The final line should be:

```text
SETUP CHECK PASSED
```

---

## 8. Run a Quick Test

Run one fresh simulation:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 1
```

`TG_FORCE_NEW=1` creates a new search run.

A successful execution should eventually print:

```text
minimum_distance: ...
1 test cases generated
output folder: ...
```

Local artifacts are written under:

```text
results/
generated_tests/
logs/
```

---

## 9. Run a Mission With a Larger Budget

Example with 100 successful simulations:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 100
```

The second positional argument is the total target simulation budget.

---

## 10. Run the Full Experiment

Run 100 simulations for each of the three missions:

```bash
./scripts/run_all_100.sh
```

The script executes:

```text
mission1: 100 simulations
mission2: 100 simulations
mission3: 100 simulations
```

Total:

```text
100 x 3 = 300 successful simulations
```

The script uses `TG_FORCE_NEW=1`, so it is intended for starting a complete fresh experiment.

---

## 11. Crash Recovery

The generator writes native recovery information under:

```text
results/tg_mcts_elites/<run_id>/
```

Important checkpoint files include:

```text
run_state.json
checkpoint/pending_candidate.json
checkpoint/results.jsonl
checkpoint/history.jsonl
checkpoint/system_errors.csv
checkpoint/invalid_candidates.csv
```

After a PC, Docker, Gazebo, PX4, or process interruption, resume the same mission **without** `TG_FORCE_NEW=1`.

Example:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The budget is interpreted as the total target.

For example, when 37 successful simulations already exist, the resumed execution continues toward 100 rather than running 100 additional simulations.

Do not use the fresh-run script to resume an interrupted mission.

---

## 12. Reproducible Random Seed

To use a fixed search seed:

```bash
TG_SEED=12345 TG_FORCE_NEW=1 \
python cli.py generate case_studies/mission1.yaml 100
```

The seed is stored in the run state.

---

## 13. Dockerfile

The repository Dockerfile is based on:

```dockerfile
FROM skhatiri/aerialist:2.0
```

Inside that project container, `AGENT=local` is used because the container already contains the Aerialist/PX4 simulation environment.

This differs from the recommended host workflow:

```text
Host workflow:      AGENT=docker
Project container:  AGENT=local
```

Do not change the host `.env` value from `docker` to `local`.

---

## 14. Aerialist Log Levels

Aerialist may display a container transcript with an `ERROR` logging level even when the simulation completed.

The execution is successful when the transcript also contains messages such as:

```text
entry - INFO - test finished
testcase - INFO - test finished
minimum_distance: ...
```

The TG-MCTS-Elites generator reports a genuine retryable infrastructure failure explicitly as a system error.

---

## 15. Generated and Local-Only Files

The following files are intentionally excluded from Git:

```text
results/
logs/
generated_tests/
*.ulg
*.bag
.env
backups/
```

They are generated during local simulation and can become large.

---

## 16. Common Problems

### `ModuleNotFoundError: No module named 'decouple'`

Activate or update the environment:

```bash
conda activate uav
conda env update -f environment.yml --prune
```

### `ModuleNotFoundError: No module named 'aerialist'`

Install the pinned host package:

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

Do not use `TG_FORCE_NEW=1`:

```bash
python cli.py generate case_studies/mission1.yaml 100
```
