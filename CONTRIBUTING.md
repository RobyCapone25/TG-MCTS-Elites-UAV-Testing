# Contributing

Contributions should preserve the competition command-line interface and the
strict simulator-attempt accounting policy.

## Development setup

```bash
conda env create -f environment.yml
conda activate uav
cp .env.example .env
./scripts/check_setup.sh
```

## Before opening a pull request

Run:

```bash
PYTHONPATH="$PWD/src" MPLBACKEND=Agg \
python -m unittest discover -s tests -v

bash -n scripts/*.sh
git diff --check
```

Do not commit generated simulator artifacts, including:

```text
results/
generated_tests/
logs/
*.ulg
*.bag
```

## Documentation requirements

Changes affecting score semantics, budget accounting, output layout, public
names, mission outcomes, or artifact retention must update the corresponding
documentation and Mermaid diagrams.

## Pull-request scope

Prefer focused commits:

1. implementation and tests;
2. documentation and repository infrastructure.

Describe any simulator runs used for validation, including mission, budget,
seed, platform, and whether `TG_FORCE_NEW=1` was used.
