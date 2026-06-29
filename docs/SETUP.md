# Setup Guide

This document explains how to install and run the TG-MCTS-Elites UAV test generator.

The project was developed for Linux and uses Docker-based simulation through Aerialist. PX4, Gazebo, and ROS are handled inside the Docker container, so they do not need to be installed manually on the host machine for the standard workflow.

---

## Tested Platform

| Component | Version / Requirement |
|---|---|
| Operating system | Linux, tested on Ubuntu |
| Python | Python 3.10 |
| Environment manager | Conda |
| Docker | Required |
| Aerialist | Docker image `skhatiri/aerialist:2.0` |
| PX4 / Gazebo | Provided inside the Aerialist Docker container |
| Simulation mode | Docker-based execution |

The expected execution chain is:

```text
Linux / Ubuntu host
    -> Conda Python environment
    -> TG-MCTS-Elites generator
    -> Docker
    -> Aerialist container
    -> PX4/Gazebo simulation
```

---

## 1. Install Docker

Docker is required because the PX4/Gazebo simulation is executed through the Aerialist Docker image.

On Ubuntu:

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

To run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
```

Then log out and log back in.

Check that Docker works:

```bash
docker run hello-world
```

---

## 2. Pull the Aerialist Docker Image

The project uses:

```text
skhatiri/aerialist:2.0
```

Pull the image:

```bash
docker pull skhatiri/aerialist:2.0
```

This image provides the simulation stack used by Aerialist, including PX4/Gazebo execution.

For the standard Docker-based workflow, you do not need to install PX4-Autopilot, PX4-Avoidance, ROS, or Gazebo manually on your Linux machine.

---

## 3. Create the Conda Environment

Create the environment:

```bash
conda env create -f environment.yml
```

Activate it:

```bash
conda activate uav
```

If the environment already exists, update it:

```bash
conda env update -f environment.yml --prune
```

The project uses Python 3.10.

---

## 4. Install Python Dependencies

The recommended way is through `environment.yml`.

If needed, install the dependencies manually:

```bash
python -m pip install -r requirements.txt
python -m pip install python-decouple matplotlib numpy pandas pyyaml munch pyparsing
```

The package `python-decouple` is required to read the `.env` configuration file.

If it is missing, you may see:

```text
ModuleNotFoundError: No module named 'decouple'
```

Fix it with:

```bash
python -m pip install python-decouple
```

---

## 5. Configure the .env File

Copy the example configuration:

```bash
cp .env.example .env
```

The default configuration is:

```text
AGENT=docker
SIMULATOR=ros
ROBOT=px4_ros
HEADLESS=True
DOCKER_IMG=skhatiri/aerialist:2.0
DOCKER_TIMEOUT=1000
```

This means the generator runs simulations through Docker using the Aerialist image `skhatiri/aerialist:2.0`.

The `.env` file is local and should not be committed to GitHub.

---

## 6. Repository Structure

The organized repository structure is:

```text
.
├── README.md
├── Dockerfile
├── environment.yml
├── requirements.txt
├── .env.example
├── cli.py
├── src/
│   ├── __init__.py
│   ├── cli.py
│   ├── random_generator.py
│   └── testcase.py
├── scripts/
│   └── run_all_100.sh
├── case_studies/
│   ├── mission1.yaml
│   ├── mission2.yaml
│   └── mission3.yaml
└── docs/
    ├── SETUP.md
    └── uml/
```

The root `cli.py` file is a launcher. The implementation is inside `src/`.

---

## 7. Run a Quick Test

Activate the environment:

```bash
conda activate uav
```

Run one simulation:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 1
```

A successful simulation should print a minimum distance, for example:

```text
minimum_distance: ...
```

and generate local outputs under:

```text
generated_tests/
results/
```

---

## 8. Run the Full Experiment

Run 100 simulations for each mission:

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

## 9. Crash Recovery

The generator supports checkpointing.

Before each simulation, the current candidate is saved as:

```text
pending_candidate.json
```

Successful simulations are saved in:

```text
results.jsonl
history.jsonl
```

If the PC, Docker, or simulator crashes, resume the interrupted mission without `TG_FORCE_NEW=1`.

Example:

```bash
python cli.py generate case_studies/mission1.yaml 100
```

The value `100` is the total target budget, not 100 additional simulations.

For example, if 37 simulations were already completed, the resumed run continues from simulation 38 and stops at 100.

---

## 10. Generated Files

The following folders are generated locally:

```text
results/
logs/
generated_tests/
```

They are intentionally ignored by Git because they can be large.

PX4 log files such as `.ulg` files are also ignored.
