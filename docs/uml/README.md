# UML Diagrams

This folder contains the Mermaid source files for the project diagrams.

The diagrams describe the architecture and execution logic of the TG-MCTS-Elites UAV test generator.

---

## Files

| File | Role |
|---|---|
| `class_diagram.mmd` | Class-level architecture |
| `execution_flow.mmd` | Full algorithm execution flow |
| `sequence_diagram.mmd` | Runtime interaction sequence |

---

## Editing With Mermaid Live Editor

To edit a diagram visually:

1. Open the corresponding `.mmd` file.
2. Copy its content.
3. Paste it into Mermaid Live Editor.
4. Modify the diagram.
5. Export the diagram if a PNG or SVG is needed.
6. Commit the updated `.mmd` source file.

---

## Why Mermaid Instead of PNG Only?

Mermaid source files are text-based.

This is better for GitHub because:

- the diagrams are version-controlled as text;
- they are easier to modify;
- they avoid low-quality PNG compression;
- GitHub can render them directly in Markdown.

The README also contains rendered Mermaid diagrams directly.
