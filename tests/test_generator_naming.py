from __future__ import annotations

import unittest

from random_generator import RandomGenerator, RandomSearchGenerator, TGMCTSElitesGenerator
from tg_mcts_elites import RandomSearchGenerator as PackageRandomSearch
from tg_mcts_elites import TGMCTSElitesGenerator as PackageGenerator


class GeneratorNamingTests(unittest.TestCase):
    def test_descriptive_generator_name_is_public(self) -> None:
        self.assertIs(PackageGenerator, TGMCTSElitesGenerator)

    def test_old_name_remains_a_compatibility_alias(self) -> None:
        self.assertIs(RandomGenerator, TGMCTSElitesGenerator)

    def test_real_random_baseline_is_public_and_distinct(self) -> None:
        self.assertIs(PackageRandomSearch, RandomSearchGenerator)
        self.assertIsNot(RandomSearchGenerator, TGMCTSElitesGenerator)


if __name__ == "__main__":
    unittest.main()
