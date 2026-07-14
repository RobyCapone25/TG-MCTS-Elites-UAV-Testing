# Changelog

All notable repository-level changes are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project has not yet published a GitHub release.

## [0.1.0] - Unreleased

### Added

- Modular TG-MCTS-Elites implementation under `src/tg_mcts_elites/`.
- Mission-derived QGroundControl path parsing and simulator-frame inference.
- Strict simulator-attempt accounting and checkpoint/resume support.
- Robustness confirmation for leading failures.
- Obstacle-geometry and trajectory-DTW diversity filtering.
- Mission-aware output folders, failure artifacts, tree plots, and progress
  plots.
- Unit tests for score semantics, mission outcomes, naming compatibility,
  mission conversion, diversity, output generation, and method contracts.
- A distinct operator-matched `RandomSearchGenerator` baseline.
- Restart-safe paired benchmark scripts, append-only event recording, atomic
  summaries, completed-run aggregation, and explicit two-seed comparison plots.
- GitHub repository checks, issue templates, and contribution guidance.

### Changed

- Adopted `TGMCTSElitesGenerator` as the descriptive public class name.
- Retained `RandomGenerator` only as a backward-compatible alias.
- Separated input compliance, mission outcome, and distance-based failure
  evidence.
- Clarified that critical proximity is not independent collision evidence.
- Harmonized documentation with strict attempt-budget semantics.

### Known limitations

- No independent collision signal is currently consumed.
- Hosted CI does not execute PX4/Gazebo simulations.
- No statistically conclusive benchmark claim is made from only two seeds.
- No software license has yet been declared.
