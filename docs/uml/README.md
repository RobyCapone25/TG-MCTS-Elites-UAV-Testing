# UML Diagrams

The Mermaid sources document the implementation under `src/tg_mcts_elites/`.

| File | Purpose |
|---|---|
| [`class_diagram.mmd`](class_diagram.mmd) | Public class, compatibility alias, mixins, data structures, and principal dependencies |
| [`execution_flow.mmd`](execution_flow.mmd) | Mission parsing, strict-budget exploration, retries, confirmation, retention, and export |
| [`sequence_diagram.mmd`](sequence_diagram.mmd) | Runtime interactions among CLI, generator, simulator, persistence, plotting, confirmation, and selection |

The diagrams are version-controlled as text and can be rendered with Mermaid
Live Editor or embedded in Markdown using Mermaid code fences.

The diagrams use `TGMCTSElitesGenerator` as the descriptive public name.
`RandomGenerator` appears only as a compatibility alias.

They also distinguish:

- generated-input compliance;
- mission outcome;
- distance-based failure evidence;
- independent collision evidence, which is not currently available.
