from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

from runtime_acl26 import (
    available_recipe_names,
    build_class_weights,
    build_model_bundle,
    build_hierarchy_map,
    build_label_names,
    create_dataloader,
    ensure_dir,
    evaluate_model,
    forward_batch,
    import_acl_loss,
    load_split_dataframe,
    resolve_runtime_recipe,
    seed_everything,
    split_train_eval_holdout,
    write_json,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", choices=available_recipe_names())
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-definition-path", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--acl-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--execution-host", default="local")
    parser.add_argument("--execution-mode", default="local")
    parser.add_argument("--execution-project-root", default="")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    seed_everything(42)
    project_root = Path(args.project_root).resolve()
    task_definition_path = Path(args.task_definition_path).resolve()
    acl_root = Path(args.acl_root).resolve()
    data_root = Path(args.data_root).resolve()
    result_json = Path(args.result_json).resolve()
    recipe_config = resolve_runtime_recipe(args.recipe, task_definition_path)

    HierarchicalSupConLoss = import_acl_loss(acl_root)

    train_frame, train_summary = load_split_dataframe(
        data_root=data_root,
        recipe_name=args.recipe,
        stage="train",
        task_definition_path=task_definition_path,
    )
    train_eval_strategy = recipe_config.get("train_eval_strategy", "dataset_eval")
    if train_eval_strategy == "holdout":
        original_train_count = len(train_frame)
        train_frame, eval_frame = split_train_eval_holdout(
            train_frame,
            holdout_fraction=float(recipe_config.get("train_eval_fraction", 0.1)),
            min_eval_samples=int(recipe_config.get("train_eval_min_samples", 64)),
            max_eval_samples=recipe_config.get("train_eval_max_samples"),
            seed=42,
        )
        train_summary["_holdout_policy"] = {
            "strategy": "holdout",
            "original_sample_count": original_train_count,
            "train_sample_count": int(len(train_frame)),
            "eval_sample_count": int(len(eval_frame)),
            "holdout_fraction": float(recipe_config.get("train_eval_fraction", 0.1)),
            "min_eval_samples": int(recipe_config.get("train_eval_min_samples", 64)),
            "max_eval_samples": recipe_config.get("train_eval_max_samples"),
        }
        eval_summary = {
            "suite": "train_holdout",
            "strategy": "holdout",
            "sample_count": int(len(eval_frame)),
            "region_labels": sorted(eval_frame["region_label"].astype(str).unique().tolist()),
        }
    else:
        eval_frame, eval_summary = load_split_dataframe(
            data_root=data_root,
            recipe_name=args.recipe,
            stage="eval",
            task_definition_path=task_definition_path,
        )
    label_names = build_label_names(task_definition_path)
    hierarchy_map = build_hierarchy_map(label_names)
    model, tokenizer = build_model_bundle(recipe_config, task_definition_path, len(label_names), acl_root)

    train_loader = create_dataloader(train_frame, label_names, tokenizer, recipe_config, shuffle=True)
    eval_loader = create_dataloader(eval_frame, label_names, tokenizer, recipe_config, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    class_weights = build_class_weights(train_frame, label_names, recipe_config.get("class_weight_mode", "none"))
    if class_weights is not None:
        class_weights = class_weights.to(device)
    criterion_ce = nn.CrossEntropyLoss(weight=class_weights)
    criterion_supcon = HierarchicalSupConLoss(hierarchy_map)
    optimizer = optim.AdamW(model.parameters(), lr=recipe_config["learning_rate"])

    max_steps = recipe_config["max_steps"]
    global_step = 0
    best_eval = {
        "dev_accuracy": 0.0,
        "macro_f1": 0.0,
        "rare_dialect_recall": 0.0,
        "loss": 0.0,
        "sample_count": 0,
    }

    model.train()
    for epoch in range(recipe_config["epochs"]):
        for batch in train_loader:
            optimizer.zero_grad()
            logits, proj_features, labels = forward_batch(model, batch, device)
            loss_ce = criterion_ce(logits, labels)
            loss_hier = torch.tensor(0.0, device=device)
            if labels.size(0) > 1:
                fine_loss, coarse_loss = criterion_supcon(proj_features, labels)
                loss_hier = fine_loss + coarse_loss
            loss = loss_ce + 0.1 * loss_hier
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            global_step += 1
            if global_step >= max_steps:
                break
        best_eval = evaluate_model(model, eval_loader, device, criterion_ce)
        if global_step >= max_steps:
            break

    checkpoint_dir = project_root / "artifacts" / "checkpoints" / args.recipe
    ensure_dir(checkpoint_dir)
    checkpoint_path = checkpoint_dir / "best_model.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "label_names": label_names,
            "hierarchy_map": hierarchy_map,
            "recipe": args.recipe,
            "recipe_protocol_id": recipe_config["protocol_id"],
            "protocol_tier": recipe_config["protocol_tier"],
            "model_track_name": recipe_config["model_track_name"],
            "model_track": recipe_config["model_track"],
            "text_enabled": recipe_config["text_enabled"],
            "saved_at": utc_now(),
        },
        checkpoint_path,
    )

    manifest = {
        "recipe": args.recipe,
        "generated_at": utc_now(),
        "train_protocol": "train_datasets",
        "eval_suite": recipe_config.get("eval_suite", "smoke"),
        "execution_host": args.execution_host,
        "execution_mode": args.execution_mode,
        "execution_project_root": args.execution_project_root,
        "source_root": str(Path(args.source_root).resolve()),
        "acl_root": str(acl_root),
        "data_root": str(data_root),
        "task_definition_path": str(task_definition_path),
        "label_names": label_names,
        "protocol_id": recipe_config["protocol_id"],
        "protocol_tier": recipe_config["protocol_tier"],
        "model_track_name": recipe_config["model_track_name"],
        "model_track": recipe_config["model_track"],
        "text_enabled": recipe_config["text_enabled"],
        "class_weight_mode": recipe_config.get("class_weight_mode", "none"),
        "train_summary": train_summary,
        "eval_summary": eval_summary,
        "train_eval_strategy": train_eval_strategy,
        "max_steps": max_steps,
        "checkpoint_artifact": str(checkpoint_path.relative_to(project_root)),
    }
    manifest_path = project_root / "artifacts" / "runtime" / f"train_manifest_{args.recipe}.json"
    write_json(manifest_path, manifest)

    latest_train = {
        "generated_at": utc_now(),
        "recipe": args.recipe,
        "protocol_id": recipe_config["protocol_id"],
        "protocol_tier": recipe_config["protocol_tier"],
        "model_track_name": recipe_config["model_track_name"],
        "model_track": recipe_config["model_track"],
        "text_enabled": recipe_config["text_enabled"],
        "class_weight_mode": recipe_config.get("class_weight_mode", "none"),
        "checkpoint_artifact": str(checkpoint_path.relative_to(project_root)),
        "train_manifest_artifact": str(manifest_path.relative_to(project_root)),
        "metrics": best_eval,
        "execution_host": args.execution_host,
        "execution_mode": args.execution_mode,
        "execution_project_root": args.execution_project_root,
        "label_count": len(label_names),
    }
    latest_train_path = project_root / "artifacts" / "metrics" / "latest_train.json"
    named_train_path = project_root / "artifacts" / "metrics" / f"train_{args.recipe}.json"
    write_json(latest_train_path, latest_train)
    write_json(named_train_path, latest_train)

    write_json(
        result_json,
        {
            "success": True,
            "summary": f"Completed the ACL26 ADI training loop for recipe '{args.recipe}'.",
            "artifacts": {
                "latest_train": str(latest_train_path.relative_to(project_root)),
                f"train_manifest_{args.recipe}": str(manifest_path.relative_to(project_root)),
                f"checkpoint_{args.recipe}": str(checkpoint_path.relative_to(project_root)),
            },
            "metrics": best_eval,
            "execution_host": args.execution_host,
            "execution_mode": args.execution_mode,
            "notes": [
                "The official baseline track is now acoustic-only; transcript features remain disabled in this recipe.",
                f"Protocol tier: {recipe_config['protocol_tier']}.",
                f"Recipe name: {args.recipe}.",
                f"Training device: {device}",
                "Labels are the 6 target regions rather than country-level dialect codes.",
                "The reserved future track is controlled transcript dual-stream, which is intentionally not enabled here.",
            ],
            "budget_cost": 20,
        },
    )


if __name__ == "__main__":
    main()
