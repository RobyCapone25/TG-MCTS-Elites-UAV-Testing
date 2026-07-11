# Documentation

This folder contains the detailed documentation for the TG-MCTS-Elites UAV test generator.

---

## Contents

| Path | Purpose |
|---|---|
| `SETUP.md` | Complete installation, configuration, verification, execution, and recovery guide |
| `uml/` | Mermaid architecture and execution diagrams |

---

## Setup Documentation

The complete setup guide is:

```text
docs/SETUP.md
```

It documents:

- Linux and Ubuntu;
- Python 3.10;
- the Conda environment;
- the Aerialist Python package;
- Docker installation and permissions;
- the pinned `skhatiri/aerialist:2.0` image;
- the distinction between host Aerialist and containerized PX4/Gazebo;
- `.env` configuration;
- automated setup verification;
- quick tests;
- full experiments;
- deterministic seeds;
- crash recovery;
- generated files;
- common setup errors.

Run the environment checker from the repository root:

```bash
./scripts/check_setup.sh
```

---

## UML Documentation

Mermaid source files are stored in:

```text
docs/uml/
```

The diagrams can be:

- reviewed directly on GitHub;
- edited as text;
- copied into Mermaid Live Editor;
- exported to SVG or PNG when necessary.
