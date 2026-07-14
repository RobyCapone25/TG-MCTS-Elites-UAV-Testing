"""Compatibility layer for the original module name.

New code should import :class:`TGMCTSElitesGenerator`.  ``RandomGenerator`` is
kept as an alias so existing competition scripts continue to run unchanged.
"""

from tg_mcts_elites.generator import RandomGenerator, TGMCTSElitesGenerator

__all__ = ["TGMCTSElitesGenerator", "RandomGenerator"]
