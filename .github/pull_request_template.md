## Summary

Describe the change and its motivation.

## Validation

- [ ] `PYTHONPATH="$PWD/src" MPLBACKEND=Agg python -m unittest discover -s tests -v`
- [ ] `bash -n scripts/*.sh`
- [ ] `git diff --check`
- [ ] Documentation updated when behavior, outputs, naming, or budget semantics changed
- [ ] No generated simulator artifacts or private configuration committed

## Simulator evidence

State the mission, budget, seed, platform, and result of any simulator run used
for validation. Write `Not run` when the change does not require simulation.

## Compatibility

Describe any effect on the competition CLI or the `RandomGenerator`
compatibility alias.
