"""Compatibility imports for UAV scenario generators.

``RandomGenerator`` remains an alias of TG-MCTS-Elites for old competition
scripts. Use ``RandomSearchGenerator`` for the actual random baseline.
"""

from tg_mcts_elites import (
    RandomGenerator,
    RandomSearchGenerator,
    TGMCTSElitesGenerator,
)

__all__ = ["TGMCTSElitesGenerator", "RandomSearchGenerator", "RandomGenerator"]
