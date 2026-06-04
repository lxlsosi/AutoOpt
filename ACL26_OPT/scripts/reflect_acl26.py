from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_spec import load_task_definition


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-definition-path", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    task_definition = load_task_definition(Path(args.task_definition_path).resolve())
    diagnosis = json.loads((project_root / "artifacts" / "analysis" / "acl26_adi_diagnosis.json").read_text(encoding="utf-8"))
    train_metrics = json.loads((project_root / "artifacts" / "metrics" / "latest_train.json").read_text(encoding="utf-8"))
    eval_metrics = json.loads((project_root / "artifacts" / "metrics" / "latest_eval.json").read_text(encoding="utf-8"))
    local_gold_eval_path = project_root / "artifacts" / "metrics" / "eval_local_gold.json"
    local_gold_eval = None
    if local_gold_eval_path.exists():
        local_gold_eval = json.loads(local_gold_eval_path.read_text(encoding="utf-8"))
    source_link = json.loads((project_root / "artifacts" / "runtime" / "source_link.json").read_text(encoding="utf-8"))
    inventory = json.loads((project_root / "artifacts" / "analysis" / "data_inventory_report.json").read_text(encoding="utf-8"))

    next_steps = [
        "Use the new shard-indexed loader and validate throughput on ECO before scaling max_steps further.",
        "Keep the automatic loop restricted to whitelist datasets until graylist datasets are explicitly validated.",
        "Decide whether ADI17 should stay acoustic-only or receive transcripts from a controlled external transcription step.",
        "Compare the serious acoustic-only baseline against the Local gold final gate before enabling any transcript-assisted track.",
    ]
    if not source_link.get("shared_source_ready_for_eco", False):
        next_steps.append("Stage ACL26_ADI training data to object storage with rclone and materialize it under /data before routing large compute to ECO machines.")

    reflection = {
        "task_name": task_definition["task_name"],
        "label_space": task_definition["label_space"],
        "diagnosis_source_of_truth": diagnosis.get("source_of_truth_guess"),
        "train_metrics": train_metrics.get("metrics", {}),
        "eval_metrics": eval_metrics.get("metrics", {}),
        "local_gold_eval_metrics": (local_gold_eval or {}).get("metrics", {}),
        "shared_source_ready_for_eco": source_link.get("shared_source_ready_for_eco", False),
        "dataset_policy_snapshot": inventory.get("datasets", {}),
        "key_blockers": [
            "The shard-indexed loader is in place, but full-recipe throughput on ECO still needs measurement before scaling beyond the first serious baseline.",
            "ADI17 has no native text field, so the transcript-assisted semantic branch remains intentionally disabled.",
            "Graylist datasets MGB3 and MGB5 cannot enter the automated loop until their labels are proven.",
            "Large ECO training still depends on valid rclone/object storage credentials plus one-time data staging under /data."
        ],
        "next_steps": next_steps,
    }

    artifact_path = project_root / "artifacts" / "analysis" / "reflection_1.json"
    write_json(artifact_path, reflection)
    write_json(
        Path(args.result_json).resolve(),
        {
            "success": True,
            "summary": "Reflected on the ACL26 ADI acoustic-only baseline and captured the next optimization blockers.",
            "artifacts": {
                "reflection_1": str(artifact_path.relative_to(project_root)),
            },
            "notes": next_steps,
            "budget_cost": 2,
        },
    )


if __name__ == "__main__":
    main()
