from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--execution-host", default="local")
    parser.add_argument("--execution-mode", default="local")
    parser.add_argument("--execution-project-root", default="")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    result_json = Path(args.result_json).resolve()
    eval_path = project_root / "artifacts" / "metrics" / "latest_eval.json"
    eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))

    reflection = {
        "generated_at": utc_now(),
        "source_eval": str(eval_path.relative_to(project_root)),
        "failure_mode": "Minority dialect recall remains below target in the baseline run.",
        "recommended_next_action": "train_balanced_recipe",
        "evidence": eval_payload["analysis"],
        "hypotheses": [
            "Use class-balanced sampling to reduce majority-dialect bias.",
            "Add stronger augmentation to close the broadcast-to-social domain gap."
        ]
    }

    reflection_path = project_root / "artifacts" / "analysis" / "reflection_1.json"
    write_json(reflection_path, reflection)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Reflected on the weak result and selected a balanced retry strategy.",
            "artifacts": {
                "reflection_1": str(reflection_path.relative_to(project_root))
            },
            "execution_host": args.execution_host,
            "execution_mode": args.execution_mode,
            "hypotheses": reflection["hypotheses"],
            "notes": [
                "The next step should not be another baseline rerun.",
                "The reflection points to class imbalance and domain mismatch.",
                f"Reflection executed on {args.execution_host} ({args.execution_mode})."
            ],
            "budget_cost": 5
        },
    )


if __name__ == "__main__":
    main()
