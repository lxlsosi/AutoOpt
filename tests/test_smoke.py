from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from autoopt.orchestrator import Orchestrator
from autoopt.project_loader import load_project
from autoopt.state_store import FileStateStore
from autoopt.workers import RuleBasedWorker


class AutoOptSmokeTest(unittest.TestCase):
    def test_arab_example_reaches_handoff_with_artifacts(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir) / "Arab"
            shutil.copytree(
                repo_root / "Arab",
                project_dir,
                ignore=shutil.ignore_patterns("artifacts", ".autoopt"),
            )

            spec, contract, walkthrough = load_project(str(project_dir / "project.json"))
            state_dir = project_dir / spec.runtime.get("state_dir", ".autoopt/jobs")
            orchestrator = Orchestrator(
                spec=spec,
                contract=contract,
                walkthrough=walkthrough,
                worker=RuleBasedWorker(),
                store=FileStateStore(str(state_dir)),
            )

            state = orchestrator.run(job_id="smoke", max_turns=12)

            self.assertEqual(state.phase, "done")
            self.assertIn("source_catalog", state.artifacts)
            self.assertIn("validated_sources", state.artifacts)
            self.assertIn("clean_dataset_manifest", state.artifacts)
            self.assertIn("macro_f1", state.best_metric)
            self.assertFalse(state.pending_jobs)
