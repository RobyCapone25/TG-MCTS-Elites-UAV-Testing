from __future__ import annotations

import unittest

from random_generator import RandomGenerator, TGMCTSElitesGenerator
from tg_mcts_elites import TGMCTSElitesGenerator as PackageGenerator


class GeneratorNamingTests(unittest.TestCase):
    def test_descriptive_generator_name_is_public(self) -> None:
        self.assertIs(PackageGenerator, TGMCTSElitesGenerator)

    def test_old_name_remains_a_compatibility_alias(self) -> None:
        self.assertIs(RandomGenerator, TGMCTSElitesGenerator)


if __name__ == "__main__":
    unittest.main()
