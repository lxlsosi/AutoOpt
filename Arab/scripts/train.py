from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_manifest(project_root: Path) -> dict:
    manifest_path = project_root / "artifacts" / "data" / "clean_dataset_manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def write_checkpoint(project_root: Path, recipe: str, content: dict) -> str:
    checkpoint_path = project_root / "artifacts" / "checkpoints" / recipe / "last.ckpt.json"
    write_json(checkpoint_path, content)
    return str(checkpoint_path.relative_to(project_root))


def baseline(
    project_root: Path,
    result_json: Path,
    execution_host: str,
    execution_mode: str,
    execution_project_root: str,
) -> None:
    manifest = load_manifest(project_root)
    print(f"[train] start baseline on {execution_host} ({execution_mode})", flush=True)
    time.sleep(2)
    train_metrics = {
        "macro_f1": 0.74,
        "rare_dialect_recall": 0.59,
        "overall_accuracy": 0.79
    }
    checkpoint_relative = write_checkpoint(
        project_root,
        "baseline",
        {
            "saved_at": utc_now(),
            "recipe": "baseline",
            "dataset_version": manifest["dataset_version"],
            "execution_host": execution_host,
            "step": 1200,
        },
    )
    train_payload = {
        "generated_at": utc_now(),
        "recipe": "baseline",
        "dataset_version": manifest["dataset_version"],
        "gpu_job_id": f"{execution_host}-gpu-baseline-001",
        "execution_host": execution_host,
        "execution_mode": execution_mode,
        "execution_project_root": execution_project_root,
        "hyperparameters": {
            "encoder": "wav2vec-style-base",
            "classifier": "linear",
            "sampling": "natural",
            "augmentation": "light"
        },
        "checkpoint_artifact": checkpoint_relative,
        "metrics": train_metrics
    }
    latest_path = project_root / "artifacts" / "metrics" / "latest_train.json"
    named_path = project_root / "artifacts" / "metrics" / "train_baseline.json"
    write_json(latest_path, train_payload)
    write_json(named_path, train_payload)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Baseline training completed; minority dialect recall remains weak.",
            "artifacts": {
                "latest_train": str(latest_path.relative_to(project_root)),
                "train_baseline": str(named_path.relative_to(project_root)),
                "baseline_checkpoint": checkpoint_relative
            },
            "metrics": train_metrics,
            "dataset_version": manifest["dataset_version"],
            "gpu_job_id": f"{execution_host}-gpu-baseline-001",
            "execution_host": execution_host,
            "execution_mode": execution_mode,
            "hypotheses": [
                "Natural sampling under-serves rare dialects.",
                "A stronger recipe should target dialect balance and domain robustness."
            ],
            "notes": [
                "Baseline is intentionally cheap and mainly diagnostic.",
                "Sudanese and Maghrebi are expected error hotspots.",
                f"Training is routed through {execution_host} ({execution_mode})."
            ],
            "budget_cost": 120
        },
    )
    print(f"[train] baseline finished on {execution_host}", flush=True)


def balanced(
    project_root: Path,
    result_json: Path,
    execution_host: str,
    execution_mode: str,
    execution_project_root: str,
) -> None:
    manifest = load_manifest(project_root)
    print(f"[train] start balanced recipe on {execution_host} ({execution_mode})", flush=True)
    time.sleep(2)
    train_metrics = {
        "macro_f1": 0.83,
        "rare_dialect_recall": 0.72,
        "overall_accuracy": 0.85
    }
    checkpoint_relative = write_checkpoint(
        project_root,
        "balanced_recipe",
        {
            "saved_at": utc_now(),
            "recipe": "balanced_recipe",
            "dataset_version": manifest["dataset_version"],
            "execution_host": execution_host,
            "step": 1800,
        },
    )
    train_payload = {
        "generated_at": utc_now(),
        "recipe": "balanced_recipe",
        "dataset_version": manifest["dataset_version"],
        "gpu_job_id": f"{execution_host}-gpu-balanced-002",
        "execution_host": execution_host,
        "execution_mode": execution_mode,
        "execution_project_root": execution_project_root,
        "hyperparameters": {
            "encoder": "wav2vec-style-base",
            "classifier": "mlp",
            "sampling": "class_balanced",
            "augmentation": "telephony_plus_noise",
            "loss": "focal"
        },
        "checkpoint_artifact": checkpoint_relative,
        "metrics": train_metrics
    }
    latest_path = project_root / "artifacts" / "metrics" / "latest_train.json"
    named_path = project_root / "artifacts" / "metrics" / "train_balanced_recipe.json"
    write_json(latest_path, train_payload)
    write_json(named_path, train_payload)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Improved training recipe completed with stronger rare-dialect recall.",
            "artifacts": {
                "latest_train": str(latest_path.relative_to(project_root)),
                "train_balanced_recipe": str(named_path.relative_to(project_root)),
                "balanced_checkpoint": checkpoint_relative
            },
            "metrics": train_metrics,
            "dataset_version": manifest["dataset_version"],
            "gpu_job_id": f"{execution_host}-gpu-balanced-002",
            "execution_host": execution_host,
            "execution_mode": execution_mode,
            "hypotheses": [
                "Balanced sampling reduces bias toward Egyptian and MSA.",
                "Domain augmentation improves robustness outside broadcast speech."
            ],
            "notes": [
                "This is the last expensive retry before a human gate.",
                "The recipe specifically targets low-resource dialect stability.",
                f"Training is routed through {execution_host} ({execution_mode})."
            ],
            "budget_cost": 180
        },
    )
    print(f"[train] balanced recipe finished on {execution_host}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", choices=["baseline", "balanced"])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--execution-host", default="local")
    parser.add_argument("--execution-mode", default="local")
    parser.add_argument("--execution-project-root", default="")
    parser.add_argument("--ssh-target", default="")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    result_json = Path(args.result_json).resolve()

    if args.recipe == "baseline":
        baseline(
            project_root,
            result_json,
            args.execution_host,
            args.execution_mode,
            args.execution_project_root,
        )
    else:
        balanced(
            project_root,
            result_json,
            args.execution_host,
            args.execution_mode,
            args.execution_project_root,
        )


if __name__ == "__main__":
    main()
