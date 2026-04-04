from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn

from runtime_acl26 import build_model_bundle, create_dataloader, evaluate_model, load_eval_suite_dataframe, resolve_runtime_recipe, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def eval_suite_version(eval_suite: str) -> str:
    if eval_suite == "local_gold":
        return "local_gold_v1"
    if eval_suite == "formal_dev":
        return "acl26_adi_formal_dev_v1"
    return "acl26_adi_dev_smoke_v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-definition-path", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--acl-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--execution-host", default="local")
    parser.add_argument("--execution-mode", default="local")
    parser.add_argument("--execution-project-root", default="")
    parser.add_argument("--eval-suite", default="smoke")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    task_definition_path = Path(args.task_definition_path).resolve()
    acl_root = Path(args.acl_root).resolve()
    data_root = Path(args.data_root).resolve()
    result_json = Path(args.result_json).resolve()

    latest_train_path = project_root / "artifacts" / "metrics" / "latest_train.json"
    latest_train = json.loads(latest_train_path.read_text(encoding="utf-8"))
    checkpoint_path = project_root / latest_train["checkpoint_artifact"]
    recipe_config = resolve_runtime_recipe(latest_train["recipe"], task_definition_path)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    label_names = checkpoint["label_names"]
    model, tokenizer = build_model_bundle(recipe_config, task_definition_path, len(label_names), acl_root)

    eval_frame, eval_summary = load_eval_suite_dataframe(
        data_root=data_root,
        eval_suite_name=args.eval_suite,
        task_definition_path=task_definition_path,
    )
    eval_loader = create_dataloader(eval_frame, label_names, tokenizer, recipe_config, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    criterion_ce = nn.CrossEntropyLoss()
    metrics = evaluate_model(model, eval_loader, device, criterion_ce)
    metrics["adaptation_readiness"] = 1.0
    if args.eval_suite == "formal_dev":
        metrics["formal_dev_accuracy"] = metrics["dev_accuracy"]
        metrics["formal_dev_macro_f1"] = metrics["macro_f1"]
    if args.eval_suite == "local_gold":
        metrics["local_gold_accuracy"] = metrics["dev_accuracy"]
        metrics["local_gold_macro_f1"] = metrics["macro_f1"]

    latest_eval = {
        "generated_at": utc_now(),
        "recipe": latest_train["recipe"],
        "protocol_id": latest_train.get("protocol_id"),
        "protocol_tier": latest_train.get("protocol_tier"),
        "model_track_name": latest_train.get("model_track_name"),
        "model_track": latest_train.get("model_track"),
        "text_enabled": latest_train.get("text_enabled"),
        "eval_suite": args.eval_suite,
        "eval_suite_version": eval_suite_version(args.eval_suite),
        "metrics": metrics,
        "eval_summary": eval_summary,
        "execution_host": args.execution_host,
        "execution_mode": args.execution_mode,
    }
    latest_eval_named_path = project_root / "artifacts" / "metrics" / f"latest_eval_{args.eval_suite}.json"
    named_eval_path = project_root / "artifacts" / "metrics" / f"eval_{args.eval_suite}.json"
    latest_eval_recipe_path = project_root / "artifacts" / "metrics" / f"latest_eval_{args.eval_suite}_{latest_train['recipe']}.json"
    named_eval_recipe_path = project_root / "artifacts" / "metrics" / f"eval_{args.eval_suite}_{latest_train['recipe']}.json"
    write_json(latest_eval_named_path, latest_eval)
    write_json(named_eval_path, latest_eval)
    write_json(latest_eval_recipe_path, latest_eval)
    write_json(named_eval_recipe_path, latest_eval)
    if args.eval_suite != "local_gold":
        write_json(project_root / "artifacts" / "metrics" / "latest_eval.json", latest_eval)

    write_json(
        result_json,
        {
            "success": True,
            "summary": f"Evaluated the ACL26 ADI baseline on the {args.eval_suite} evaluation suite.",
            "artifacts": {
                f"latest_eval_{args.eval_suite}": str(latest_eval_named_path.relative_to(project_root)),
                f"eval_{args.eval_suite}": str(named_eval_path.relative_to(project_root)),
                f"latest_eval_{args.eval_suite}_{latest_train['recipe']}": str(latest_eval_recipe_path.relative_to(project_root)),
                f"eval_{args.eval_suite}_{latest_train['recipe']}": str(named_eval_recipe_path.relative_to(project_root)),
            },
            "metrics": metrics,
            "eval_suite": args.eval_suite,
            "eval_suite_version": eval_suite_version(args.eval_suite),
            "execution_host": args.execution_host,
            "execution_mode": args.execution_mode,
            "notes": [
                "This evaluation restores the same acoustic-only baseline architecture that produced the checkpoint.",
                "This evaluation uses only datasets that are allowed by the current task definition.",
                "formal_dev is the frozen intermediate benchmark; local_gold is the final gold-eval gate.",
                "If local_gold fails because of missing files, sync the mirrored audio first.",
            ],
            "budget_cost": 8,
        },
    )


if __name__ == "__main__":
    main()
