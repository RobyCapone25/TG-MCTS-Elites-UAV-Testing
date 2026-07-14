from __future__ import annotations

import inspect
import unittest

from tg_mcts_elites.generator import TGMCTSElitesGenerator


class MethodContractTests(unittest.TestCase):
    def test_periodic_snapshot_calls_existing_progress_method(self) -> None:
        generator = object.__new__(TGMCTSElitesGenerator)
        self.assertTrue(callable(getattr(generator, "_save_progress_plots", None)))

        source = inspect.getsource(TGMCTSElitesGenerator._process_evaluated_node)
        self.assertIn("_save_progress_plots()", source)
        self.assertNotIn("_save_progress_plot()", source)

    def test_noncompleted_mission_is_not_reclassified_as_input_noncompliance(self) -> None:
        source = inspect.getsource(TGMCTSElitesGenerator._run_simulation_once)
        self.assertIn("failure_evidence = self._failure_evidence", source)
        self.assertNotIn(
            "mission did not complete and no independent collision signal is available",
            source,
        )

    def test_confirmation_artifact_method_exists(self) -> None:
        generator = object.__new__(TGMCTSElitesGenerator)
        method = getattr(generator, "_save_confirmation_failure_artifacts", None)
        self.assertTrue(callable(method))

        parameters = inspect.signature(method).parameters
        self.assertIn("result", parameters)
        self.assertIn("simulation_index", parameters)
        self.assertIn("node", parameters)
        self.assertIn("base_simulation_attempt", parameters)


if __name__ == "__main__":
    unittest.main()
