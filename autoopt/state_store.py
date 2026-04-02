from __future__ import annotations

import json
from pathlib import Path

from autoopt.models import JobState


class FileStateStore:
    def __init__(self, state_dir: str) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def state_path(self, job_id: str) -> Path:
        return self.state_dir / f"{job_id}.json"

    def load(self, job_id: str) -> JobState | None:
        path = self.state_path(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return JobState.from_dict(data)

    def save(self, state: JobState) -> Path:
        path = self.state_path(state.job_id)
        state.touch()
        path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
