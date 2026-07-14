# Documentation

| Path | Contents |
|---|---|
| [`ALGORITHM.md`](ALGORITHM.md) | TG-MCTS-Elites search objective, mission path, MCTS, MAP-Elites, reward, confirmation, ranking, and diversity |
| [`BENCHMARK.md`](BENCHMARK.md) | Operator-matched random-search baseline, paired execution, restart safety, metrics, aggregation, and plots |
| [`OUTPUTS.md`](OUTPUTS.md) | Run namespaces, checkpoints, retained artifacts, benchmark summaries, plots, and ranking exports |
| [`SETUP.md`](SETUP.md) | Installation, runtime configuration, validation, execution, benchmarking, recovery, and troubleshooting |
| [`uml/class_diagram.mmd`](uml/class_diagram.mmd) | Modular classes, mixins, random-search baseline, and benchmark recorder |
| [`uml/execution_flow.mmd`](uml/execution_flow.mmd) | Algorithm selection, strict-budget search, confirmation, benchmark recording, retention, and export |
| [`uml/sequence_diagram.mmd`](uml/sequence_diagram.mmd) | Runtime interactions among CLI, both generators, simulator, persistence, recorder, and selector |

The documentation distinguishes:

1. **input compliance**: whether the generated obstacle configuration satisfies
   the competition constraints;
2. **mission outcome**: `completed`, `not_completed`, or `unknown`;
3. **failure evidence**: the observed distance band and its relationship to
   mission completion;
4. **search algorithm**: TG-MCTS-Elites or operator-matched random search;
5. **benchmark status**: completed summaries only are aggregated.

The current implementation does not consume an independent collision signal.
