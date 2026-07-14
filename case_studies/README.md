# Case Studies

This directory contains the supplied UAV missions and their Aerialist
case-study configurations. The generator does not modify mission waypoints; it
generates obstacle configurations around the inferred mission path.

## Main files

| File | Role |
|---|---|
| `mission1.yaml` | Mission 1 Aerialist configuration |
| `mission2.yaml` | Mission 2 Aerialist configuration |
| `mission3.yaml` | Mission 3 Aerialist configuration |
| `mission1.plan` | Mission 1 QGroundControl plan |
| `mission2.plan` | Mission 2 QGroundControl plan |
| `mission3.plan` | Mission 3 QGroundControl plan |
| `mission-commands.csv` | Reference command information |
| `mission-params.csv` | Reference mission parameter information |
| `*.png` | Reference mission and case-study figures |

Local `.ulg` files are ignored and are not part of the versioned case studies.

## Run a mission

From the repository root:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission1.yaml 10
```

The second argument is a strict simulator-attempt budget, not a guaranteed
number of successful evaluations or returned failures.

Example:

```bash
TG_FORCE_NEW=1 python cli.py generate case_studies/mission2.yaml 100
```

This allows at most 100 real simulator executions for the Mission 2 run,
including retries and confirmation reruns.

## Mission-path use

The generator:

1. resolves the `.plan` referenced by the YAML;
2. converts geographic waypoints to a local metric path;
3. evaluates eight possible axis/sign mappings;
4. samples initial scenarios and path-oriented mutations from the inferred
   simulator-frame path.

## Generated outputs

Generated data are stored outside this directory:

```text
results/
generated_tests/
logs/
```

These paths are ignored because simulator output can become large.
